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
    def __init__(self, cap=500):
        self._cap = cap
        self._events = []
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def version(self):
        return self._seq

    def emit(self, source, event_type, data):
        try:
            json.dumps(data)
        except (TypeError, ValueError):
            data = None
        event_type = derive_event_type(event_type, data)
        with self._lock:
            self._seq += 1
            self._events.append({
                "seq": self._seq, "ts": time.time(), "source": source,
                "type": str(event_type), "summary": _summarize(event_type, data),
                "data": data,
            })
            if len(self._events) > self._cap:
                self._events = self._events[-self._cap:]

    def since(self, seq):
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]


BUS = LiveEventBus()
