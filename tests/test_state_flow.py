# tests/test_state_flow.py
import sys
import json
sys.path.insert(0, ".")


def _complete_swml():
    from python.steps.step11_complete import CompleteAgent
    a = CompleteAgent(route="/step11")
    swml = a._render_swml()
    import json
    return json.loads(swml) if isinstance(swml, str) else swml


def test_buddy_uses_contexts_steps():
    swml = _complete_swml()
    ai = [v for s in swml["sections"]["main"] if isinstance(s, dict) for k, v in s.items() if k == "ai"][0]
    steps = {s["name"]: s for s in ai["prompt"]["contexts"]["default"]["steps"]}
    topics = {"weather", "joke", "time", "math"}
    assert set(steps) == {"greeting", "wrap_up"} | topics
    # tool scoping: each topic step exposes exactly its own tool(s)
    assert steps["weather"]["functions"] == ["get_weather"]
    assert steps["joke"]["functions"] == ["tell_joke"]
    assert set(steps["time"]["functions"]) == {"get_current_time", "get_current_date"}
    assert steps["math"]["functions"] == ["calculate"]
    # mesh navigation: greeting reaches every topic and the wrap-up directly;
    # every topic reaches every OTHER topic and the wrap-up (no hub menu)
    assert set(steps["greeting"]["valid_steps"]) == topics | {"wrap_up"}
    for t in topics:
        assert set(steps[t]["valid_steps"]) == (topics - {t}) | {"wrap_up"}, t
    assert steps["wrap_up"]["valid_steps"] == []
    # conversational steps expose no business tool
    # set_functions("none") renders as "functions": "none" in the SWML
    for conv in ("greeting", "wrap_up"):
        assert "functions" not in steps[conv] or steps[conv]["functions"] in ([], None, "none")


def test_post_prompt_requests_json():
    from python.steps.step11_complete import CompleteAgent
    a = CompleteAgent(route="/step11")
    swml = a._render_swml()
    s = swml if isinstance(swml, str) else __import__("json").dumps(swml)
    # the post_prompt must ask for the structured JSON shape
    assert "topics_handled" in s and "decisions" in s and "outcome" in s


def test_extract_state_flow():
    import call_store
    raw = {
        "call_log": [
            {"role": "system-log", "action": "session_start", "metadata": {"step": "greeting", "context": "default"}},
            {"role": "system-log", "action": "step_change", "timestamp": 1,
             "metadata": {"from_step": "greeting", "from_index": 0, "to_step": "weather",
                          "to_index": 1, "trigger": "ai_function", "context": "default"}},
            {"role": "system-log", "action": "function_call", "timestamp": 2,
             "metadata": {"function": "get_weather", "native": False, "step": "weather", "step_index": 1}},
        ]
    }
    sf = call_store.extract_state_flow(raw)
    assert sf["initial_step"] == "greeting"
    assert len(sf["transitions"]) == 1
    assert sf["transitions"][0]["to_step"] == "weather"
    assert sf["transitions"][0]["trigger"] == "ai_function"
    assert sf["function_calls"][0]["function"] == "get_weather"


def test_extract_state_flow_empty():
    import call_store
    sf = call_store.extract_state_flow({"call_log": []})
    assert sf == {"transitions": [], "function_calls": [], "initial_step": None}


def test_normalize_includes_state_flow():
    import call_store
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", {
        "call_log": [{"role": "system-log", "action": "step_change", "timestamp": 1,
                      "metadata": {"from_step": "greeting", "to_step": "jokes", "trigger": "ai_function"}}]
    })
    assert "state_flow" in rec
    assert rec["state_flow"]["transitions"][0]["to_step"] == "jokes"


def test_extract_state_flow_bad_metadata():
    import call_store
    # truthy non-dict metadata must not raise
    raw = {"call_log": [{"role": "system-log", "action": "step_change", "metadata": "bad"}]}
    sf = call_store.extract_state_flow(raw)
    assert sf["transitions"][0]["to_step"] is None


def test_weather_tool_forces_step_when_configured():
    from python.steps._weather import register_weather_tool

    class _Cap:
        def __init__(self): self.tool = None
        def define_tool(self, **kw): self.tool = kw

    # WITH advance_to_step: a change_step action must be present
    # (no workshop agent passes this anymore; kept as a reference capability)
    cap = _Cap()
    register_weather_tool(cap, advance_to_step="some_step")
    res = cap.tool["handler"]({"city": "Chicago"}, {})
    actions = res.action  # SwaigFunctionResult.action is a plain list of dicts
    assert any(isinstance(a, dict) and a.get("change_step") == "some_step" for a in actions)

    # WITHOUT advance_to_step (the path every workshop agent uses): no change_step action at all
    cap2 = _Cap()
    register_weather_tool(cap2)
    res2 = cap2.tool["handler"]({"city": "Chicago"}, {})
    actions2 = res2.action
    assert not any(isinstance(a, dict) and "change_step" in a for a in actions2)


def test_joke_tool_has_no_forced_step():
    # Delivery happens inside the joke step now; the handler must NOT force
    # a step change (the old joke_react micro-step is gone).
    from python.steps.step11_complete import CompleteAgent
    a = CompleteAgent(route="/step11")
    res = a.on_tell_joke({}, {})
    actions = res.action  # SwaigFunctionResult.action is a plain list of dicts
    assert not any(isinstance(x, dict) and "change_step" in x for x in actions)


def test_transcript_excludes_system_log():
    import call_store
    rec = call_store.normalize_post_prompt("complete-agent", "/step11", {
        "call_log": [
            {"role": "user", "content": "hi"},
            {"role": "system-log", "action": "step_change", "content": "greeting -> weather", "metadata": {}},
            {"role": "assistant", "content": "hello"},
        ]
    })
    roles = [t["role"] for t in rec["transcript"]]
    assert roles == ["user", "assistant"]
    assert "system-log" not in roles


def test_buddy_records_calls_stereo_wav():
    swml = _complete_swml()
    main = swml["sections"]["main"]
    rc = [v for s in main if isinstance(s, dict) for k, v in s.items() if k == "record_call"]
    assert rc, "step11 SWML must contain a record_call verb"
    assert rc[0]["format"] == "wav"
    assert rc[0]["stereo"] is True
    keys = [k for s in main if isinstance(s, dict) for k in s.keys()]
    assert keys.index("record_call") < keys.index("ai")


def test_step09_does_not_record():
    import json
    from python.steps.step09_polish import PolishedAgent
    a = PolishedAgent(route="/step09")
    swml = a._render_swml()
    swml = json.loads(swml) if isinstance(swml, str) else swml
    keys = [k for s in swml["sections"]["main"] if isinstance(s, dict) for k in s.keys()]
    assert "record_call" not in keys


def test_greeting_mentions_recording():
    swml = _complete_swml()
    ai = [v for s in swml["sections"]["main"] if isinstance(s, dict) for k, v in s.items() if k == "ai"][0]
    steps = {s["name"]: s for s in ai["prompt"]["contexts"]["default"]["steps"]}
    text = json.dumps(steps["greeting"])
    assert "record" in text.lower()


def test_buddy_streams_debug_events():
    swml = _complete_swml()
    ai = [v for s in swml["sections"]["main"] if isinstance(s, dict) for k, v in s.items() if k == "ai"][0]
    params = ai.get("params") or {}
    assert params.get("debug_webhook_url"), "debug_webhook_url must be set"
    assert "/debug_events" in params["debug_webhook_url"]
    assert params.get("debug_webhook_level", 0) >= 1


def test_step09_has_no_debug_webhook():
    import json
    from python.steps.step09_polish import PolishedAgent
    a = PolishedAgent(route="/step09")
    swml = a._render_swml()
    swml = json.loads(swml) if isinstance(swml, str) else swml
    ai = [v for s in swml["sections"]["main"] if isinstance(s, dict) for k, v in s.items() if k == "ai"][0]
    assert not (ai.get("params") or {}).get("debug_webhook_url")


def test_debug_event_handler_feeds_live_bus():
    import live_events
    from python.steps.step11_complete import CompleteAgent
    a = CompleteAgent(route="/step11")
    before = live_events.BUS.version
    a._on_debug_event("barge", {"content": "user interrupted"})
    evs = live_events.BUS.since(before)
    assert evs and evs[0]["source"] == "ai" and evs[0]["type"] == "barge"
