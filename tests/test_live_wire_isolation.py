"""Live Wire events must be tagged with the originating workshop session so the
SSE feed can be filtered per attendee. Fixes the leak where every attendee saw
the presenter's call events (noted by Leonard Graham, Nick Amhaus)."""
from live_events import LiveEventBus, derive_session_id


def _envelope(event_name, sid=None, call_id=None, **inner):
    call_info = {}
    if sid is not None:
        call_info["global_data"] = {"workshop_session_id": sid}
    if call_id is not None:
        call_info["call_id"] = call_id
    return {"call_info": call_info, event_name: inner}


def test_derive_session_id_from_envelope():
    data = _envelope("ai_response", sid="sess-A", call_id="call-1", text="hi")
    assert derive_session_id(data) == ("sess-A", "call-1")


def test_emit_tags_event_from_payload():
    bus = LiveEventBus()
    bus.emit("ai", "ai_response", _envelope("ai_response", sid="sess-A", call_id="c1"))
    assert bus.since(0)[-1]["session_id"] == "sess-A"


def test_explicit_session_id_wins():
    bus = LiveEventBus()
    bus.emit("swaig", "tell_joke", {"result": "ha"}, session_id="sess-B")
    assert bus.since(0)[-1]["session_id"] == "sess-B"


def test_call_id_learning_map_backfills_later_events():
    bus = LiveEventBus()
    bus.emit("ai", "step_change", _envelope("step_change", sid="sess-C", call_id="c9"))
    bus.emit("ai", "ai_response", _envelope("ai_response", call_id="c9", text="yo"))
    assert bus.since(0)[-1]["session_id"] == "sess-C"


def test_since_filters_by_session():
    bus = LiveEventBus()
    bus.emit("ai", "x", _envelope("x", sid="A", call_id="a"))
    bus.emit("ai", "y", _envelope("y", sid="B", call_id="b"))
    a_only = bus.since(0, session_id="A")
    assert [e["type"] for e in a_only] == ["x"]


def test_untagged_event_excluded_from_session_feed():
    bus = LiveEventBus()
    bus.emit("ai", "z", {"no": "call_info"})  # unresolvable -> session_id None
    assert bus.since(0, session_id="A") == []
    assert bus.since(0)[-1]["session_id"] is None


def test_resolver_tags_ai_event_by_call_info(monkeypatch):
    """Real AI debug events have call_info.project_id but no global_data; the
    injected resolver must tag them so they aren't dropped."""
    import live_events
    monkeypatch.setattr(live_events, "_session_resolver",
                        lambda ci: "sess-P" if ci.get("project_id") == "proj-1" else None)
    bus = LiveEventBus()
    # envelope with call_info.project_id and NO global_data (the real shape)
    data = {"call_info": {"project_id": "proj-1", "call_id": "cc"},
            "ai_response": {"text": "hello"}}
    bus.emit("ai", "ai_response", data)
    assert bus.since(0)[-1]["session_id"] == "sess-P"


def test_resolver_seeds_learning_map_for_later_events(monkeypatch):
    import live_events
    calls = {"n": 0}
    def resolver(ci):
        calls["n"] += 1
        return "sess-Q"
    monkeypatch.setattr(live_events, "_session_resolver", resolver)
    bus = LiveEventBus()
    base = {"call_info": {"project_id": "p", "call_id": "ck"}}
    bus.emit("ai", "a", {**base, "a": {}})
    bus.emit("ai", "b", {"call_info": {"call_id": "ck"}, "b": {}})  # only call_id
    assert [e["session_id"] for e in bus.since(0)] == ["sess-Q", "sess-Q"]
    assert calls["n"] == 1  # second event inherited from the map, no re-resolve


def test_drain_advances_cursor_past_non_matching(monkeypatch):
    """drain must report a cursor past non-matching events so the SSE loop
    cannot lose an event emitted between a since() and a version read."""
    bus = LiveEventBus()
    bus.emit("ai", "x", {"call_info": {"call_id": "1"}, "x": {}}, session_id="X")
    evs, cur = bus.drain(0, session_id="Y")
    assert evs == [] and cur == 1            # nothing for Y, but cursor advanced
    bus.emit("ai", "y", {"call_info": {"call_id": "2"}, "y": {}}, session_id="Y")
    evs2, cur2 = bus.drain(cur, session_id="Y")
    assert [e["type"] for e in evs2] == ["y"] and cur2 == 2
