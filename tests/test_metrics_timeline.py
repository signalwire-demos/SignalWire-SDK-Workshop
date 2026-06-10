# tests/test_metrics_timeline.py
import sys
sys.path.insert(0, ".")
import call_store

US = 1_000_000  # 1 second in microseconds


def _payload():
    base = 1_000_000_000_000
    return {
        "call_start_date": base,
        "call_answer_date": base + 600_000,        # ring 0.6s
        "ai_start_date":   base + 700_000,          # setup 0.1s
        "ai_end_date":     base + 700_000 + 120 * US,  # AI session 120s
        "call_end_date":   base + 700_000 + 121 * US,  # teardown 1s
        "total_input_tokens": 1000, "total_output_tokens": 50,
        "total_tts_chars": 300, "total_tts_chars_per_min": 150,
        "total_asr_minutes": 1.5, "total_minutes": 2,
        "times": [
            {"answer_time": 0.8, "response_word_count": 5, "tokens": 10, "tps": 12.0},
            {"answer_time": 1.6, "response_word_count": 9, "tokens": 18, "tps": 11.0},
        ],
        "swaig_log": [
            {"command_name": "get_weather", "post_response": {"response": "72F", "action": [{"set_global_data": {"x": 1}}]}},
        ],
        "call_log": [
            {"role": "system-log", "action": "session_start", "metadata": {"step": "greeting"}},
            {"role": "assistant", "content": "Hi there friend", "audio_latency": 1000, "timestamp": base + 701_000, "start_timestamp": base + 701_000, "end_timestamp": base + 702_000},
            {"role": "user", "content": "weather please", "confidence": 0.98, "timestamp": base + 703_000, "start_timestamp": base + 703_000, "end_timestamp": base + 704_000},
            {"role": "tool", "function_name": "get_weather", "latency": 800, "execution_latency": 800, "function_latency": 600, "timestamp": base + 705_000, "start_timestamp": base + 705_000, "end_timestamp": base + 706_000},
            {"role": "assistant", "content": "It is seventy two", "audio_latency": 2000, "timestamp": base + 707_000, "start_timestamp": base + 707_000, "end_timestamp": base + 708_000},
        ],
    }


def test_metrics_durations_and_latency():
    m = call_store.extract_metrics(_payload())
    assert m["durations"]["ai_session_s"] == 120.0
    assert m["durations"]["ring_s"] == 0.6
    a = m["latency"]["assistant"]
    assert a["count"] == 2
    assert a["avg"] == 1500          # (1000 + 2000)/2
    assert a["fastest"] == 1000 and a["slowest"] == 2000
    assert a["under_target"] == 1    # only the 1000ms one is < 1200
    assert m["rating"] == "Good"     # avg 1500 -> Good
    assert m["latency"]["tool"]["count"] == 1


def test_metrics_conversation_tokens_swaig_billing():
    m = call_store.extract_metrics(_payload())
    c = m["conversation"]
    assert c["turns"] == 3           # assistant, user, assistant
    assert c["user_messages"] == 1
    assert c["agent_responses"] == 2
    assert round(c["asr_confidence_avg"], 1) == 98.0
    assert m["tokens"]["input"] == 1000
    assert m["tokens"]["peak_tps"] == 12
    assert m["swaig"]["total_calls"] == 1
    assert m["swaig"]["function_names"] == ["get_weather"]
    assert m["swaig"]["action_types"] == 1
    assert m["billing"]["total_minutes"] == 2


def test_timeline_phases_and_lanes():
    t = call_store.extract_timeline(_payload())
    names = [p["name"] for p in t["phases"]]
    assert names == ["Ring", "Setup", "AI Session", "Teardown"]
    ai = next(p for p in t["phases"] if p["name"] == "AI Session")
    assert ai["ms"] == 120_000
    assert len(t["lanes"]["assistant"]) == 2
    assert len(t["lanes"]["user"]) == 1
    assert len(t["lanes"]["tool"]) == 1
    assert t["bounds"]["ai_start"] and t["bounds"]["ai_end"]


def test_extract_empty_is_safe():
    assert call_store.extract_metrics({}) is not None
    assert call_store.extract_metrics({"call_log": []})["latency"]["assistant"] is None
    tl = call_store.extract_timeline({})
    assert tl["phases"] == [] and tl["lanes"]["user"] == []


def test_normalize_includes_metrics_and_timeline():
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", _payload())
    assert "metrics" in rec and "timeline" in rec
    assert rec["metrics"]["conversation"]["turns"] == 3
