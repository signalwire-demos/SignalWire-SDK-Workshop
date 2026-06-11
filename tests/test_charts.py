# tests/test_charts.py
import sys
sys.path.insert(0, ".")
import call_store


def _payload():
    return {
        "call_log": [
            {"role": "system-log", "action": "session_start", "metadata": {"step": "greeting"}},
            {"role": "assistant", "content": "Hi!", "latency": 700, "utterance_latency": 900,
             "audio_latency": 1100, "timestamp": 1},
            {"role": "user", "content": "weather in Chicago please", "confidence": 0.97,
             "speaking_to_turn_detection": 300, "turn_detection_to_final_event": 150,
             "speaking_to_final_event": 450, "timestamp": 2},
            {"role": "tool", "function_name": "get_weather", "latency": 800,
             "execution_latency": 800, "function_latency": 600, "timestamp": 3},
            {"role": "user", "content": "barged", "confidence": 0.5,
             "speaking_to_turn_detection": -120, "turn_detection_to_final_event": 80,
             "speaking_to_final_event": 200, "merge_count": 2, "timestamp": 4},
            {"role": "assistant", "content": "Bye", "latency": 2000, "timestamp": 5},
        ],
        "times": [
            {"answer_time": 1.1, "response_word_count": 12, "tokens": 40, "tps": 36.4},
            {"answer_time": 0.2, "response_word_count": 0, "tokens": 1, "tps": 0},
            {"answer_time": 0.9, "response_word_count": 8, "tokens": 30, "tps": float("inf")},
        ],
    }


def test_latency_breakdown_segments_and_labels():
    ch = call_store.extract_charts(_payload())
    rows = ch["latency_breakdown"]
    assert [r["label"] for r in rows] == ["R1", "T1", "R2"]
    r1 = rows[0]
    assert r1["role"] == "assistant"
    assert r1["llm"] == 700
    assert r1["utterance"] == 200       # 900 - 700
    assert r1["audio"] == 200           # 1100 - 900
    assert r1["total"] == 1100          # audio_latency wins
    t1 = rows[1]
    assert t1["role"] == "tool" and t1["total"] == 800
    r2 = rows[2]
    assert r2["llm"] == 2000 and r2["utterance"] == 0 and r2["audio"] == 0 and r2["total"] == 2000


def test_latency_stats():
    st = call_store.extract_charts(_payload())["latency_stats"]
    assert st["assistant"] == {"min": 1100, "avg": 1550, "max": 2000}
    assert st["tool"] == {"min": 800, "avg": 800, "max": 800}


def test_tps_sanitized_and_tool_tagged():
    tps = call_store.extract_charts(_payload())["tps"]
    assert tps[0]["is_tool"] is False and tps[0]["tps"] == 36
    assert tps[1]["is_tool"] is True
    assert tps[2]["tps"] == 0           # inf sanitized to 0


def test_asr_rows_with_barge_and_merge():
    asr = call_store.extract_charts(_payload())["asr"]
    assert len(asr) == 2
    assert asr[0]["confidence_pct"] == 97
    assert asr[0]["s2t"] == 300 and asr[0]["t2f"] == 150
    assert asr[0]["barge"] is False and asr[0]["merged"] is False
    assert asr[1]["barge"] is True
    assert asr[1]["s2t"] == 0           # negative clamped
    assert asr[1]["t2f"] == 200         # barge -> uses speaking_to_final_event
    assert asr[1]["merged"] is True


def test_roles_and_swaig_by_command():
    ch = call_store.extract_charts(_payload())
    assert ch["roles"] == {"system-log": 1, "assistant": 2, "user": 2, "tool": 1}
    sw = ch["swaig_by_command"]
    assert sw == [{"name": "get_weather", "count": 1,
                   "avg_execution_ms": 800, "avg_function_ms": 600}]


def test_charts_defensive_on_garbage():
    ch = call_store.extract_charts(None)
    assert ch["latency_breakdown"] == [] and ch["tps"] == [] and ch["asr"] == []
    assert ch["roles"] == {} and ch["swaig_by_command"] == []


def test_normalize_includes_charts():
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", _payload())
    assert "charts" in rec
    assert rec["charts"]["latency_breakdown"][0]["label"] == "R1"
