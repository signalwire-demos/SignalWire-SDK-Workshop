"""Single source of truth for captured post-prompt calls (admin dashboard).

Thread-safe and JSON-persisted (mirrors session_store.py) so a restart does not
lose the room's calls. A monotonic `version` counter lets the SSE endpoint detect
new records by polling — robust across the SDK's sync/async/thread boundaries.
"""
import json
import math
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


def extract_state_flow(raw_data):
    """Reconstruct the agent's step-machine flow from call_log system-log events.

    Mirrors postpromptviewer's extractStateFlow: step_change entries become
    transitions, function_call entries become function nodes, session_start gives
    the initial step. Defensive: anything missing degrades to empty/None.
    """
    raw_data = raw_data if isinstance(raw_data, dict) else {}
    transitions, function_calls, initial_step = [], [], None
    for e in (raw_data.get("call_log") or []):
        if not isinstance(e, dict) or e.get("role") != "system-log":
            continue
        md = e.get("metadata")
        md = md if isinstance(md, dict) else {}
        action = e.get("action")
        if action == "step_change":
            transitions.append({
                "from_step": md.get("from_step"),
                "from_index": md.get("from_index"),
                "to_step": md.get("to_step"),
                "to_index": md.get("to_index"),
                "trigger": md.get("trigger"),
                "context": md.get("context"),
                "timestamp": e.get("timestamp"),
                "content": e.get("content"),
            })
        elif action == "function_call":
            function_calls.append({
                "function": md.get("function"),
                "native": md.get("native"),
                "step": md.get("step"),
                "step_index": md.get("step_index"),
                "timestamp": e.get("timestamp"),
            })
        elif action == "session_start" and initial_step is None:
            initial_step = md.get("step")
    return {"transitions": transitions, "function_calls": function_calls, "initial_step": initial_step}


def _us_to_sec(us):
    return (us or 0) / 1_000_000


def _mean(vals):
    return sum(vals) / len(vals) if vals else 0


def _percentile(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _word_count(s):
    return len(s.split()) if isinstance(s, str) and s.strip() else 0


def _num(x):
    return x if isinstance(x, (int, float)) else 0


def extract_metrics(raw_data):
    """Compute headline call metrics from the post-prompt payload.

    Ported from postpromptviewer's computeMetrics. Defensive: missing data
    degrades to None/0, never raises.
    """
    raw_data = raw_data if isinstance(raw_data, dict) else {}
    cl = [e for e in (raw_data.get("call_log") or []) if isinstance(e, dict)]
    times = [t for t in (raw_data.get("times") or []) if isinstance(t, dict)]

    cs, ca = _num(raw_data.get("call_start_date")), _num(raw_data.get("call_answer_date"))
    a0, a1, ce = _num(raw_data.get("ai_start_date")), _num(raw_data.get("ai_end_date")), _num(raw_data.get("call_end_date"))
    durations = {
        "call_total_s": round(_us_to_sec((ce or a1) - cs), 1) if cs else None,
        "ai_session_s": round(_us_to_sec(a1 - a0), 1) if (a1 and a0) else None,
        "ring_s": round(_us_to_sec(ca - cs), 1) if (ca and cs) else None,
        "setup_s": round(_us_to_sec(a0 - ca), 1) if (a0 and ca) else None,
        "teardown_s": round(_us_to_sec(ce - a1), 1) if (ce and a1) else None,
    }

    def headline(e):
        return e.get("audio_latency") or e.get("utterance_latency") or e.get("latency") or 0

    assistant = [headline(e) for e in cl if e.get("role") == "assistant"
                 and (e.get("latency") is not None or e.get("audio_latency") is not None or e.get("utterance_latency") is not None)]
    tool = [(e.get("latency") or e.get("execution_latency") or 0) for e in cl
            if e.get("role") == "tool" and e.get("timestamp")]

    def stats(items):
        if not items:
            return None
        s = sorted(items)
        return {"avg": round(sum(items) / len(items)), "fastest": min(items), "slowest": max(items),
                "median": round(s[len(s) // 2]), "count": len(items),
                "under_target": sum(1 for t in items if t < 1200)}

    a_stats, t_stats = stats(assistant), stats(tool)
    ans_times = [t.get("answer_time") for t in times
                 if isinstance(t.get("answer_time"), (int, float)) and t["answer_time"] > 0 and t.get("response_word_count", 0) > 0]
    if a_stats:
        a_stats["p95"] = round(_percentile(ans_times, 95) * 1000) if ans_times else None
    avg = a_stats["avg"] if a_stats else None
    rating = ("Excellent" if avg < 1200 else "Good" if avg < 1800 else "Fair" if avg < 2500 else "Needs Improvement") if avg is not None else "N/A"

    turns, last, total_words, by_role = 0, None, 0, {}
    for e in cl:
        r = e.get("role")
        by_role[r] = by_role.get(r, 0) + 1
        total_words += _word_count(e.get("content"))
        if r in ("user", "assistant") and r != last:
            turns += 1
            last = r
    agent_responses = sum(1 for e in cl if e.get("role") == "assistant"
                          and isinstance(e.get("content"), str) and e["content"].strip()
                          and (e.get("audio_latency") or e.get("utterance_latency") or e.get("latency")))
    user_msgs = [e for e in cl if e.get("role") == "user"]
    confs = [e.get("confidence") for e in user_msgs if isinstance(e.get("confidence"), (int, float))]
    resp_wcs = [t.get("response_word_count", 0) for t in times if t.get("response_word_count", 0) > 0]
    conversation = {
        "turns": turns, "user_messages": len(user_msgs), "agent_responses": agent_responses,
        "total_words": total_words,
        "avg_response_words": round(_mean(resp_wcs)) if resp_wcs else 0,
        "asr_confidence_avg": round(_mean(confs) * 100, 1) if confs else None,
        "by_role": by_role,
    }

    tps = [t.get("tps") for t in times if isinstance(t.get("tps"), (int, float)) and t["tps"] > 0]
    tokens = {
        "input": raw_data.get("total_input_tokens"), "output": raw_data.get("total_output_tokens"),
        "avg_tps": round(_mean(tps)) if tps else 0, "peak_tps": round(max(tps)) if tps else 0,
        "wire_input": raw_data.get("total_wire_input_tokens"), "wire_output": raw_data.get("total_wire_output_tokens"),
    }

    swl = [e for e in (raw_data.get("swaig_log") or []) if isinstance(e, dict)]
    exec_l = [e.get("execution_latency") for e in cl if e.get("role") == "tool" and isinstance(e.get("execution_latency"), (int, float))]
    func_l = [e.get("function_latency") for e in cl if e.get("role") == "tool" and isinstance(e.get("function_latency"), (int, float))]
    action_types = set()
    for e in swl:
        resp = e.get("post_response") if isinstance(e.get("post_response"), dict) else {}
        for a in (resp.get("action") or []):
            if isinstance(a, dict):
                action_types.update(a.keys())
    swaig = {
        "total_calls": len(swl),
        "avg_execution_ms": round(_mean(exec_l)) if exec_l else None,
        "avg_function_ms": round(_mean(func_l)) if func_l else None,
        "action_types": len(action_types),
        "function_names": sorted({e.get("command_name") for e in swl if e.get("command_name")}),
    }

    tm = _num(raw_data.get("total_minutes"))
    billing = {
        "tts_chars": raw_data.get("total_tts_chars"), "tts_chars_per_min": raw_data.get("total_tts_chars_per_min"),
        "asr_minutes": raw_data.get("total_asr_minutes"), "total_minutes": raw_data.get("total_minutes"),
        "call_rate_per_min": round(turns / tm, 1) if tm else None,
    }

    return {"durations": durations, "latency": {"assistant": a_stats, "tool": t_stats},
            "rating": rating, "conversation": conversation, "tokens": tokens,
            "swaig": swaig, "billing": billing}


def extract_timeline(raw_data):
    """Phase bar + per-role swimlane segments for the Timeline view. Defensive."""
    raw_data = raw_data if isinstance(raw_data, dict) else {}
    cl = [e for e in (raw_data.get("call_log") or []) if isinstance(e, dict)]
    cs, ca = _num(raw_data.get("call_start_date")), _num(raw_data.get("call_answer_date"))
    a0, a1, ce = _num(raw_data.get("ai_start_date")), _num(raw_data.get("ai_end_date")), _num(raw_data.get("call_end_date"))

    phases = []

    def ph(name, start, end):
        if start and end and end > start:
            phases.append({"name": name, "start": start, "end": end, "ms": round((end - start) / 1000)})

    ph("Ring", cs, ca)
    ph("Setup", ca, a0)
    ph("AI Session", a0, a1)
    ph("Teardown", a1, ce)

    lanes = {"user": [], "assistant": [], "tool": [], "say": []}
    for e in cl:
        r = e.get("role")
        start = e.get("start_timestamp") or e.get("timestamp")
        end = e.get("end_timestamp") or e.get("timestamp")
        if r == "user":
            lanes["user"].append({"start": start, "end": end, "text": e.get("content"), "confidence": e.get("confidence")})
        elif r == "assistant":
            lanes["assistant"].append({"start": start, "end": end, "text": e.get("content"), "latency": e.get("latency"), "barged": bool(e.get("barged"))})
        elif r == "tool":
            lanes["tool"].append({"start": start, "end": end, "name": e.get("function_name")})
        elif r == "system-log" and e.get("action") == "manual_say":
            lanes["say"].append({"start": start, "end": end, "text": e.get("content")})

    return {"phases": phases, "lanes": lanes, "bounds": {"ai_start": a0 or cs, "ai_end": a1 or ce}}


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
        if isinstance(e, dict) and e.get("role") != "system-log"
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
        "state_flow": extract_state_flow(raw_data),
        "metrics": extract_metrics(raw_data),
        "timeline": extract_timeline(raw_data),
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
