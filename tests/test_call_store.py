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
    "caller_id_number": "+13125550100",
    "caller_id_name": "+13125550100",
    "project_id": "11111111-2222-3333-4444-555555555555",
    "space_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
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
    "SWMLCall": {"to": "+13125550199", "from": "+13125550100", "direction": "inbound"},
    "SWMLVars": {"ai_result": "ok"},
    "global_data": {"caller_id_number": "+13125550100"},
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
    assert rec["meta"]["caller_id_num"] == "+13125550100"
    assert rec["meta"]["to"] == "+13125550199"
    assert rec["meta"]["from"] == "+13125550100"
    assert rec["meta"]["direction"] == "inbound"


def test_normalize_tools_fallback_to_call_log_when_no_swaig_log():
    payload = {k: v for k, v in REAL_PAYLOAD.items() if k != "swaig_log"}
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", payload)
    assert len(rec["tools"]) == 1
    assert rec["tools"][0]["name"] == "tell_joke"
    # result paired from the following role:"tool" message's content
    assert "dad joke" in (rec["tools"][0]["result"] or "")


def test_transcript_entries_carry_metric_badges():
    raw = {
        "call_log": [
            {"role": "assistant", "content": "Hi!", "latency": 700,
             "utterance_latency": 900, "audio_latency": 1100,
             "tool_calls": [{"function": {"name": "get_weather"}}]},
            {"role": "user", "content": "hello", "confidence": 0.93,
             "barge_count": 1, "merge_count": 2, "metadata": {"barged": True}},
            {"role": "assistant", "content": "slow", "latency": 2600},
            {"role": "system-log", "action": "noop", "content": "x"},
        ],
    }
    rec = call_store.normalize_post_prompt("a", "/r", raw)
    t = rec["transcript"]
    assert len(t) == 3                      # system-log still excluded
    a1 = t[0]
    assert a1["latency"] == 700 and a1["audio_latency"] == 1100
    assert a1["rating"] == "Excellent"      # headline 1100 < 1200
    assert a1["tool_calls"] == 1
    u = t[1]
    assert u["confidence"] == 0.93 and u["barge_count"] == 1
    assert u["merge_count"] == 2 and u["barged"] is True
    a2 = t[2]
    assert a2["rating"] == "Needs Improvement"


def test_transcript_plain_entries_stay_minimal():
    rec = call_store.normalize_post_prompt("a", "/r", {
        "call_log": [{"role": "user", "content": "hi"}]})
    assert rec["transcript"][0] == {"role": "user", "content": "hi"}


def test_summary_includes_substituted():
    rec = call_store.normalize_post_prompt("a", "/r", {
        "post_prompt_data": {"raw": "r", "substituted": "s", "parsed": [{"k": 1}]}})
    assert rec["summary"]["substituted"] == "s"


def test_extract_global_data_sections():
    gd = call_store.extract_global_data({
        "global_data": {"workshop_session_id": "abc"},
        "SWMLVars": {"userVariables": {"ua": "x"}, "record_call_url": "u", "extra": 1},
        "SWMLCall": {"call_id": "c1", "direction": "inbound"},
        "params": {"verbose_logs": True},
        "prompt_vars": {"ai_instructions": "…"},
        "previous_contexts": [{"role": "system"}],
    })
    assert gd["global_data"] == {"workshop_session_id": "abc"}
    assert gd["user_variables"] == {"ua": "x"}
    assert gd["swml_vars"] == {"record_call_url": "u", "extra": 1}   # userVariables removed
    assert gd["call_metadata"]["call_id"] == "c1"
    assert gd["params"] == {"verbose_logs": True}
    assert gd["prompt_vars"] == {"ai_instructions": "…"}
    assert gd["previous_contexts"] == [{"role": "system"}]


def test_extract_global_data_omits_empty_sections():
    assert call_store.extract_global_data({"global_data": {}}) == {}
    assert call_store.extract_global_data(None) == {}


def test_normalize_includes_global_data():
    rec = call_store.normalize_post_prompt("a", "/r", {"global_data": {"k": "v"}})
    assert rec["global_data"] == {"global_data": {"k": "v"}}


def test_extract_recording_from_swml_vars():
    rec = call_store.extract_recording({
        "SWMLVars": {"record_call_url": "https://files.example/r.wav",
                     "record_call_result": "success", "record_call_start": 123}})
    assert rec == {"url": "https://files.example/r.wav", "result": "success", "start": 123}


def test_extract_recording_absent():
    assert call_store.extract_recording({}) == {"url": None, "result": None, "start": None}
    assert call_store.extract_recording(None)["url"] is None


def test_normalize_includes_recording():
    rec = call_store.normalize_post_prompt("a", "/r", {
        "SWMLVars": {"record_call_url": "u"}})
    assert rec["recording"]["url"] == "u"
