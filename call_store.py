"""Single source of truth for captured post-prompt calls (admin dashboard).

Thread-safe and JSON-persisted (mirrors session_store.py) so a restart does not
lose the room's calls. A monotonic `version` counter lets the SSE endpoint detect
new records by polling — robust across the SDK's sync/async/thread boundaries.
"""
import json
import os
import threading
import time

# Pluggable correlation hook. main.py installs a resolver that maps a raw
# post-prompt payload to the originating session {space, project_id, session_id}.
# Default: no correlation (returns None).
_session_resolver = None


def set_session_resolver(fn):
    global _session_resolver
    _session_resolver = fn


def _first(d, *keys):
    """Return the first present, truthy value among nested-safe top-level keys."""
    for k in keys:
        if isinstance(d, dict) and d.get(k):
            return d[k]
    return None


def normalize_post_prompt(agent_name, agent_route, raw_data):
    """Turn a raw post-prompt POST body into a normalized CallRecord dict.

    Defensive: extracts whatever is present; missing fields degrade to
    None/[] rather than raising. Exact payload shape: see
    docs/signalwire-agents/docs/post_data_complete_reference.md
    """
    raw_data = raw_data if isinstance(raw_data, dict) else {}

    ppd = raw_data.get("post_prompt_data") or {}
    summary_raw = ppd.get("raw") if isinstance(ppd, dict) else None
    summary_parsed = ppd.get("parsed") if isinstance(ppd, dict) else None

    # Transcript: prefer processed call_log, fall back to raw_call_log.
    transcript = raw_data.get("call_log") or raw_data.get("raw_call_log") or []
    transcript = [
        {"role": e.get("role"), "content": e.get("content")}
        for e in transcript
        if isinstance(e, dict)
    ]

    # Tool/function calls: SignalWire delivers these in `swaig_log` — each entry
    # carries the function name (`command_name`), its arguments (`command_arg`),
    # and the function's return under `post_response.response`. This is the
    # reliable source. Fall back to call_log assistant `tool_calls` (result in
    # the following role:"tool" message's `content`; note the real payload's
    # tool_call_id is often null, so pair results to calls by document order).
    tools = []
    swaig_log = raw_data.get("swaig_log") or []
    if swaig_log:
        for e in swaig_log:
            if not isinstance(e, dict):
                continue
            resp = e.get("post_response")
            result = resp.get("response") if isinstance(resp, dict) else resp
            tools.append({
                "name": e.get("command_name") or "unknown",
                "args": e.get("command_arg"),
                "result": result,
            })
    else:
        for e in (raw_data.get("call_log") or []):
            if not isinstance(e, dict):
                continue
            for tc in (e.get("tool_calls") or []):
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                tools.append({
                    "name": fn.get("name") or "unknown",
                    "args": fn.get("arguments"),
                    "result": None,
                })
            if e.get("role") == "tool":
                content = e.get("content")
                for t in tools:               # attach to earliest unfilled call
                    if t["result"] is None:
                        t["result"] = content
                        break

    swml_call = raw_data.get("SWMLCall") or {}
    if not isinstance(swml_call, dict):
        swml_call = {}
    swml_vars = raw_data.get("SWMLVars") or raw_data.get("prompt_vars") or {}
    call_id = raw_data.get("call_id") or f"call-{int(time.time() * 1000)}"

    # SWAIG execution log: the ground truth for debugging what each function call
    # actually did. For DataMap functions this shows the external URL SignalWire
    # hit; for define_tool functions, the agent's own /swaig endpoint. The raw
    # response + any error flags make a misbehaving tool obvious on the dashboard.
    swaig = []
    for e in (raw_data.get("swaig_log") or []):
        if not isinstance(e, dict):
            continue
        resp = e.get("post_response")
        response_text = resp.get("response") if isinstance(resp, dict) else resp
        swaig.append({
            "name": e.get("command_name"),
            "args": e.get("command_arg"),
            "url": e.get("url"),
            "response": response_text,
            "error": e.get("parse_error") or e.get("protocol_error") or e.get("error"),
            "http_code": e.get("http_code"),
            "epoch_time": e.get("epoch_time"),
        })

    rec = {
        "call_id": call_id,
        "received_at": time.time(),
        "agent_name": agent_name,
        "agent_route": agent_route,
        "summary": {"raw": summary_raw, "parsed": summary_parsed},
        "transcript": transcript,
        "tools": tools,
        "swaig": swaig,
        "meta": {
            # Real payload uses caller_id_number (top level) and SWMLCall.to/from.
            "caller_id_num": (raw_data.get("caller_id_number")
                              or raw_data.get("caller_id_num")
                              or _first(swml_call, "from", "from_number")),
            "caller_id_name": raw_data.get("caller_id_name"),
            "to": _first(swml_call, "to", "to_number") or _first(swml_vars, "to"),
            "from": _first(swml_call, "from", "from_number") or _first(swml_vars, "from"),
            "direction": swml_call.get("direction"),
        },
        "session": _session_resolver(raw_data) if _session_resolver else None,
        "raw": raw_data,
    }
    return rec


class CallStore:
    def __init__(self, path=None):
        self._path = path
        self._calls = []          # newest-first
        self._ids = set()
        self._lock = threading.Lock()
        self.version = 0

    def record(self, agent_name, agent_route, raw_data):
        rec = normalize_post_prompt(agent_name, agent_route, raw_data)
        with self._lock:
            if rec["call_id"] in self._ids:
                return rec
            self._ids.add(rec["call_id"])
            self._calls.insert(0, rec)
            self.version += 1
        self.save()
        return rec

    def all(self):
        with self._lock:
            return list(self._calls)

    def clear(self):
        with self._lock:
            self._calls = []
            self._ids = set()
            self.version += 1
        self.save()

    def save(self):
        if not self._path:
            return
        with self._lock:
            snapshot = json.dumps(self._calls)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(snapshot)
        except OSError as e:
            print(f"[call_store] save failed: {e}", flush=True)

    def load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[call_store] ignoring unreadable calls file: {e}", flush=True)
            return
        if isinstance(data, list):
            with self._lock:
                self._calls = data
                self._ids = {c.get("call_id") for c in data}


# Module singleton shared by agents (on_summary) and main.py (endpoints).
STORE = CallStore(path=".workshop_calls.json")
STORE.load()
