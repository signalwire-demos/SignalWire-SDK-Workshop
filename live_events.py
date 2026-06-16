"""Live Wire event bus: in-memory ring buffer of real-time call events.

Fed by the step11 agent's debug-event webhook and its tool handlers; drained
by the public /api/live-events SSE for the workshop Live Wire panel.
Thread-safe, version-counted (same convention as call_store/function_health).
"""
import json
import threading
import time


# Payload keys that identify a record but say nothing about WHAT happened;
# never use them as a derived type or summary bit.
_BORING_KEYS = frozenset((
    "call_id", "channel", "timestamp", "ts", "caller_id_name",
    "caller_id_number", "project_id", "space_id", "version", "content_type",
    "content_disposition", "node_id", "tag",
))

_ROLE_TYPES = {"assistant": "ai_response", "user": "caller_speech",
               "system": "system_prompt", "tool": "tool_result"}


# Optional correlation hook: fn(call_info: dict) -> session_id | None.
# Live debug payloads carry call_info.project_id (not global_data), so the app
# wires this to map a project to its attendee session, the same signal
# post-prompt correlation uses. Stays None in unit tests that don't set it.
_session_resolver = None


def set_session_resolver(fn):
    global _session_resolver
    _session_resolver = fn


def session_id_from_global_data(raw_data):
    """Session id stamped into a SWAIG request's global_data at SWML render.
    Tool-handler emits (whose payloads carry no call_info) pass this explicitly."""
    gd = raw_data.get("global_data") if isinstance(raw_data, dict) else None
    sid = gd.get("workshop_session_id") if isinstance(gd, dict) else None
    return sid if isinstance(sid, str) and sid else None


def derive_event_type(event_type, data):
    """A presentable type for a debug event, derived from the payload when
    the SDK couldn't name it.

    The agents SDK labels any debug POST without a top-level 'label' or
    'action' key as "unknown" — and the platform's real payloads carry
    neither. Until the platform documents the schema, classify by the keys
    we can see; a payload we can't classify still names its first
    informative key so no row ever reads bare "unknown".
    """
    if event_type and str(event_type) != "unknown":
        return str(event_type)
    if not isinstance(data, dict):
        return "unknown"
    # Platform envelope (verified live): {"call_info": {...}, "<event_name>": {...}}.
    if "call_info" in data:
        inner = [k for k in data if k != "call_info"]
        if len(inner) == 1:
            return inner[0]
    for key in ("event_type", "type", "label", "event"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v
    if isinstance(data.get("action"), str) and data["action"].strip():
        return data["action"]
    role = data.get("role")
    if isinstance(role, str) and role:
        return _ROLE_TYPES.get(role, f"conversation:{role}")
    fname = data.get("command_name") or data.get("function_name") or data.get("function")
    if isinstance(fname, str) and fname:
        return f"function:{fname}"
    if data.get("step_name") or data.get("step"):
        return "step_change"
    if "utterance" in data or "lattice" in data:
        return "speech_detected"
    if "latency" in data or "audio_latency" in data:
        return "latency_report"
    for k in data:
        if k not in _BORING_KEYS:
            return f"event:{k}"
    return "unknown"


def derive_session_id(data):
    """Extract (session_id, call_id) from a debug-event payload, if present.

    The verified platform envelope is {"call_info": {...}, "<event_name>": {...}}.
    The workshop session id rides in call_info.global_data.workshop_session_id
    (stamped at SWML render), and call_info.call_id identifies the call across
    all of its events. Returns (None, None) for anything it can't read.
    """
    if not isinstance(data, dict):
        return None, None
    ci = data.get("call_info")
    if not isinstance(ci, dict):
        return None, None
    gd = ci.get("global_data") if isinstance(ci.get("global_data"), dict) else {}
    sid = gd.get("workshop_session_id")
    call_id = ci.get("call_id")
    return (sid if isinstance(sid, str) and sid else None,
            call_id if isinstance(call_id, str) and call_id else None)


def _summarize(event_type, data):
    if isinstance(data, dict):
        # Envelope payloads keep their facts one level down, keyed by the
        # event name; summarize that inner dict instead of the wrapper.
        inner = data.get(event_type)
        if isinstance(inner, dict):
            data = inner
        bits = []
        # 'url' is deliberately absent: post_prompt.url embeds a one-time
        # creds-bearing token and the summary is publicly streamed.
        for k in ("content", "text", "utterance", "step", "step_name",
                  "function", "command_name", "name", "city", "arguments",
                  "response", "latency", "result", "error", "filler_type",
                  "source", "type", "reason", "duration_ms", "model",
                  "tts_voice", "language", "barge_type", "normalized"):
            v = data.get(k)
            if isinstance(v, (str, int, float)) and str(v).strip():
                bits.append(f"{k}={str(v)[:60]}")
            if len(bits) >= 3:
                break
        if bits:
            return f"{event_type} · " + " · ".join(bits)
    return str(event_type)


class LiveEventBus:
    def __init__(self, cap=500, call_map_cap=500):
        self._cap = cap
        self._events = []
        self._lock = threading.Lock()
        self._seq = 0
        self._call_sid = {}          # call_id -> session_id (bounded learning map)
        self._call_map_cap = call_map_cap

    @property
    def version(self):
        return self._seq

    def _resolve_sid(self, session_id, data):
        """Decide a session id for an event. Priority: explicit arg -> payload
        envelope (call_info.global_data) -> call_id learning map -> resolver
        (correlates call_info, e.g. by project_id). Seeds the learning map when
        a sid is found alongside a call_id. Caller must hold _lock."""
        payload_sid, call_id = derive_session_id(data)
        sid = session_id or payload_sid
        if not sid and call_id and call_id in self._call_sid:
            sid = self._call_sid[call_id]
        if not sid and _session_resolver and isinstance(data, dict):
            ci = data.get("call_info")
            if isinstance(ci, dict):
                try:
                    sid = _session_resolver(ci)
                except Exception:
                    sid = None
        if call_id and sid:
            if call_id not in self._call_sid and len(self._call_sid) >= self._call_map_cap:
                self._call_sid.pop(next(iter(self._call_sid)), None)
            self._call_sid[call_id] = sid
        return sid

    def emit(self, source, event_type, data, session_id=None):
        try:
            json.dumps(data)
        except (TypeError, ValueError):
            data = None
        event_type = derive_event_type(event_type, data)
        with self._lock:
            sid = self._resolve_sid(session_id, data)
            self._seq += 1
            self._events.append({
                "seq": self._seq, "ts": time.time(), "source": source,
                "type": str(event_type), "summary": _summarize(event_type, data),
                "data": data, "session_id": sid,
            })
            if len(self._events) > self._cap:
                self._events = self._events[-self._cap:]

    def since(self, seq, session_id=None):
        with self._lock:
            return [e for e in self._events
                    if e["seq"] > seq
                    and (session_id is None or e.get("session_id") == session_id)]

    def drain(self, seq, session_id=None):
        """Return (matching events with seq>`seq`, cursor) atomically. cursor is
        the highest seq assigned so far, so a caller can advance past
        non-matching events without a separate version read (avoids a
        lost-event race under concurrent emits)."""
        with self._lock:
            evs = [e for e in self._events
                   if e["seq"] > seq
                   and (session_id is None or e.get("session_id") == session_id)]
            return evs, self._seq


BUS = LiveEventBus()
