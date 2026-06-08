"""Unit tests for the post-prompt CallStore. No server, no network."""
import call_store


SAMPLE_PAYLOAD = {
    "call_id": "abc-123",
    "caller_id_num": "+15551234567",
    "caller_id_name": "Jane Doe",
    "post_prompt_data": {
        "raw": "Caller asked about weather in Chicago; Buddy gave the forecast.",
        "parsed": [{"topic": "weather", "city": "Chicago"}],
    },
    "call_log": [
        {"role": "user", "content": "what's the weather in chicago"},
        {"role": "assistant", "content": "It's 78 degrees and overcast."},
    ],
    "SWMLVars": {"to": "+15559998888", "from": "+15551234567"},
}


def test_normalize_extracts_core_fields():
    rec = call_store.normalize_post_prompt("weather-joke-agent", "/step08", SAMPLE_PAYLOAD)
    assert rec["call_id"] == "abc-123"
    assert rec["agent_name"] == "weather-joke-agent"
    assert rec["agent_route"] == "/step08"
    assert rec["summary"]["raw"].startswith("Caller asked about weather")
    assert rec["summary"]["parsed"] == [{"topic": "weather", "city": "Chicago"}]
    assert rec["transcript"] == [
        {"role": "user", "content": "what's the weather in chicago"},
        {"role": "assistant", "content": "It's 78 degrees and overcast."},
    ]
    assert rec["meta"]["caller_id_num"] == "+15551234567"
    assert rec["raw"] == SAMPLE_PAYLOAD


def test_normalize_degrades_gracefully_on_empty_payload():
    rec = call_store.normalize_post_prompt("x", None, {})
    assert rec["call_id"]            # synthesized, non-empty
    assert rec["summary"]["raw"] is None
    assert rec["transcript"] == []
    assert rec["tools"] == []
    assert rec["session"] is None


def test_record_orders_newest_first_and_dedups(tmp_path):
    store = call_store.CallStore(path=str(tmp_path / "calls.json"))
    store.record("agent-a", "/step08", {**SAMPLE_PAYLOAD, "call_id": "c1"})
    store.record("agent-b", "/step09", {**SAMPLE_PAYLOAD, "call_id": "c2"})
    store.record("agent-b", "/step09", {**SAMPLE_PAYLOAD, "call_id": "c2"})  # dup
    calls = store.all()
    assert [c["call_id"] for c in calls] == ["c2", "c1"]   # newest first, deduped


def test_version_increments_on_record_and_clear(tmp_path):
    store = call_store.CallStore(path=str(tmp_path / "calls.json"))
    assert store.version == 0
    store.record("a", "/s", {**SAMPLE_PAYLOAD, "call_id": "c1"})
    assert store.version == 1
    store.clear()
    assert store.version == 2
    assert store.all() == []


def test_persistence_round_trip(tmp_path):
    path = str(tmp_path / "calls.json")
    s1 = call_store.CallStore(path=path)
    s1.record("a", "/s", {**SAMPLE_PAYLOAD, "call_id": "c1"})
    s2 = call_store.CallStore(path=path)
    s2.load()
    assert [c["call_id"] for c in s2.all()] == ["c1"]


def test_session_resolver_tags_records(tmp_path):
    # Resolver maps the called number (+15559998888) to a session.
    def resolver(raw):
        to = (raw.get("SWMLVars") or {}).get("to")
        if to == "+15559998888":
            return {"space": "demo.signalwire.com", "project_id": "PX-1", "session_id": "s1"}
        return None

    call_store.set_session_resolver(resolver)
    try:
        store = call_store.CallStore(path=str(tmp_path / "c.json"))
        store.record("a", "/step08", SAMPLE_PAYLOAD)             # matches
        store.record("a", "/step08", {**SAMPLE_PAYLOAD, "call_id": "c9", "SWMLVars": {}})  # no match
        by_id = {c["call_id"]: c for c in store.all()}
        assert by_id["abc-123"]["session"]["project_id"] == "PX-1"
        assert by_id["c9"]["session"] is None
    finally:
        call_store.set_session_resolver(None)   # don't leak into other tests


def test_record_call_helper_feeds_store(monkeypatch, tmp_path):
    from python.steps import _summary_capture
    store = call_store.CallStore(path=str(tmp_path / "c.json"))
    monkeypatch.setattr(_summary_capture, "STORE", store)

    class FakeAgent:
        def get_name(self): return "weather-joke-agent"
        route = "/step08"

    _summary_capture.record_call(FakeAgent(), SAMPLE_PAYLOAD)
    assert [c["agent_name"] for c in store.all()] == ["weather-joke-agent"]
    assert store.all()[0]["agent_route"] == "/step08"


# Mirrors the REAL post-prompt payload observed from a live call (2026-06-08):
# tool calls + results live in `swaig_log` (tool_call_id in call_log is null),
# caller/dialed numbers in `caller_id_number` + `SWMLCall`, project in `project_id`.
REAL_PAYLOAD = {
    "call_id": "real-1",
    "caller_id_number": "+14803769009",
    "caller_id_name": "+14803769009",
    "project_id": "5d30e1ba-32c2-4d62-b94c-4855c2ba739e",
    "space_id": "304597b9-4d2b-4049-aee0-a303468b5eeb",
    "post_prompt_data": {
        "raw": "Caller asked for a joke and the weather in Chicago.",
        "parsed": [{"topic": "weather", "city": "Chicago"}],
    },
    "call_log": [
        {"role": "system", "content": "You are Buddy."},
        {"role": "user", "content": "tell me a joke"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "57938be5", "type": "function",
             "function": {"name": "tell_joke", "arguments": "{}"}},
        ]},
        {"role": "tool", "function_name": "tell_joke", "tool_call_id": None,
         "content": "Tool result below.\nHere's a dad joke: submarine took a dive."},
        {"role": "assistant", "content": "Here's a dad joke: submarine took a dive."},
    ],
    "swaig_log": [
        {"command_name": "tell_joke", "command_arg": "{}",
         "post_response": {"response": "Here's a dad joke: submarine took a dive."}},
        {"command_name": "get_weather", "command_arg": "{\"city\":\"Chicago\"}",
         "post_response": {"response": "Weather in Chicago: overcast, 78F."}},
    ],
    "SWMLCall": {"to": "+18152425477", "from": "+14803769009", "direction": "inbound"},
    "SWMLVars": {"ai_result": "ok"},
    "global_data": {"caller_id_number": "+14803769009"},
}


def test_normalize_extracts_tools_from_swaig_log_with_results():
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", REAL_PAYLOAD)
    assert len(rec["tools"]) == 2
    by_name = {t["name"]: t for t in rec["tools"]}
    assert by_name["tell_joke"]["result"] == "Here's a dad joke: submarine took a dive."
    assert by_name["get_weather"]["args"] == "{\"city\":\"Chicago\"}"
    assert by_name["get_weather"]["result"] == "Weather in Chicago: overcast, 78F."


def test_normalize_transcript_keeps_role_and_content():
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", REAL_PAYLOAD)
    roles = [t["role"] for t in rec["transcript"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]


def test_normalize_meta_reads_caller_and_swmlcall():
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", REAL_PAYLOAD)
    assert rec["meta"]["caller_id_num"] == "+14803769009"
    assert rec["meta"]["to"] == "+18152425477"
    assert rec["meta"]["from"] == "+14803769009"
    assert rec["meta"]["direction"] == "inbound"


def test_normalize_tools_fallback_to_call_log_when_no_swaig_log():
    payload = {k: v for k, v in REAL_PAYLOAD.items() if k != "swaig_log"}
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", payload)
    assert len(rec["tools"]) == 1
    assert rec["tools"][0]["name"] == "tell_joke"
    # result paired from the following role:"tool" message's content
    assert "dad joke" in (rec["tools"][0]["result"] or "")
