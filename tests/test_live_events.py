"""Tests for live_events.py ring-buffer bus and /api/live-events SSE endpoint.

Task 1 of the Live Wire Browser-Call Redesign.
"""
import sys
sys.path.insert(0, ".")
import live_events


def _fresh():
    return live_events.LiveEventBus(cap=5)


def test_emit_and_since():
    bus = _fresh()
    bus.emit("ai", "session_start", {"x": 1})
    bus.emit("swaig", "get_weather", {"city": "Denver"})
    evs = bus.since(0)
    assert len(evs) == 2
    assert evs[0]["source"] == "ai" and evs[0]["type"] == "session_start"
    assert evs[0]["seq"] == 1 and evs[1]["seq"] == 2
    assert bus.since(evs[1]["seq"]) == []
    assert bus.version == 2


def test_ring_cap_drops_oldest():
    bus = _fresh()
    for i in range(8):
        bus.emit("ai", f"e{i}", {})
    evs = bus.since(0)
    assert len(evs) == 5 and evs[0]["type"] == "e3" and evs[-1]["seq"] == 8


def test_summary_and_bad_data_never_raise():
    bus = _fresh()
    bus.emit("swaig", "boom", object())          # non-serializable
    e = bus.since(0)[0]
    assert e["data"] is None and isinstance(e["summary"], str)


class _MockRequest:
    """Minimal Request stand-in for tests: never disconnects."""
    async def is_disconnected(self):
        return False


def test_sse_endpoint_streams_new_events():
    """The /api/live-events SSE endpoint is public and replays recent events.

    We emit a uniquely-named probe into BUS before calling the route handler
    directly; the generator replays BUS.since(0)[-20:] first, so the probe
    arrives in the very first yielded chunk.  We consume until we see it.

    Note: TestClient.stream() hangs on this app's AgentServer ASGI app due to
    a sync/async bridge issue in the streaming transport layer; we call the
    async handler directly via asyncio.run to avoid the deadlock.
    """
    import asyncio
    import main
    live_events.BUS.emit("ai", "sse_probe", {"k": "v"})

    async def _collect():
        resp = await main.live_events_stream(_MockRequest())
        # Confirm the StreamingResponse carries the right media type
        assert resp.media_type == "text/event-stream"
        body = ""
        async for chunk in resp.body_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode()
            body += chunk
            if "sse_probe" in body:
                break
        return body

    body = asyncio.run(_collect())
    assert "event: live" in body
    assert "sse_probe" in body


# ---------------------------------------------------------------------------
# Tool emit tests (Step 4)
# ---------------------------------------------------------------------------

import requests as _requests
from python.steps import _weather


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_GEO = {"results": [{"name": "Chicago", "latitude": 41.85, "longitude": -87.65}]}
_FORECAST = {
    "current": {
        "temperature_2m": 72.0,
        "relative_humidity_2m": 60,
        "apparent_temperature": 74.0,
        "weather_code": 1,
    }
}


def _mock_open_meteo(monkeypatch, geo=_GEO, forecast=_FORECAST):
    def fake_get(url, params=None, timeout=None, headers=None):
        if "geocoding" in url:
            return _FakeResp(geo)
        return _FakeResp(forecast)
    monkeypatch.setattr(_requests, "get", fake_get)


def test_register_weather_tool_with_live_emit_true(monkeypatch):
    """When live_emit=True (step11), a get_weather call lands in BUS."""
    _mock_open_meteo(monkeypatch)
    from signalwire_agents import AgentBase, SwaigFunctionResult
    agent = AgentBase(name="test-weather-emit", route="/test-we")
    _weather.register_weather_tool(agent, live_emit=True)

    before = live_events.BUS.version
    fn = agent._tool_registry._swaig_functions["get_weather"]
    fn.handler({"city": "Chicago"}, {})
    evs = live_events.BUS.since(before)
    assert evs, "expected a live event from get_weather with live_emit=True"
    assert evs[0]["source"] == "swaig"
    assert evs[0]["type"] == "get_weather"


def test_register_weather_tool_with_live_emit_false(monkeypatch):
    """When live_emit=False (default; step08/09), no event is emitted."""
    _mock_open_meteo(monkeypatch)
    from signalwire_agents import AgentBase
    agent = AgentBase(name="test-weather-noemit", route="/test-wne")
    _weather.register_weather_tool(agent, live_emit=False)

    before = live_events.BUS.version
    fn = agent._tool_registry._swaig_functions["get_weather"]
    fn.handler({"city": "Chicago"}, {})
    assert live_events.BUS.version == before, "step08/09 path must not emit"


def test_on_tell_joke_emits_live_event(monkeypatch):
    """step11 joke handler emits a swaig/tell_joke event on success."""
    joke_payload = {"id": "abc", "joke": "Why did the chicken cross the road? To get to the other side!"}

    def fake_get(url, headers=None, timeout=None):
        return _FakeResp(joke_payload)
    monkeypatch.setattr(_requests, "get", fake_get)

    from python.steps.step11_complete import CompleteAgent
    agent = CompleteAgent(route="/test-step11")
    before = live_events.BUS.version
    agent.on_tell_joke({}, {})
    evs = live_events.BUS.since(before)
    assert evs, "expected a live event from on_tell_joke"
    assert evs[0]["source"] == "swaig"
    assert evs[0]["type"] == "tell_joke"


def test_on_tell_joke_emits_on_error(monkeypatch):
    """step11 joke handler emits a swaig/tell_joke event even on network error."""
    def boom(url, headers=None, timeout=None):
        raise _requests.RequestException("network down")
    monkeypatch.setattr(_requests, "get", boom)

    from python.steps.step11_complete import CompleteAgent
    agent = CompleteAgent(route="/test-step11-err")
    before = live_events.BUS.version
    agent.on_tell_joke({}, {})
    evs = live_events.BUS.since(before)
    assert evs, "expected a live event from on_tell_joke on error path"
    assert evs[0]["source"] == "swaig"
    assert evs[0]["type"] == "tell_joke"


def test_live_events_route_is_registered():
    import main
    assert any(getattr(r, "path", None) == "/api/live-events"
               for r in main.server.app.routes)


def test_sse_payload_excludes_raw_data():
    """The public SSE must publish summaries only — raw debug payloads can
    embed creds-bearing webhook URLs."""
    import asyncio
    import main
    live_events.BUS.emit("ai", "scrub_probe", {"secret_url": "http://u:p@h/x"})

    async def first_frames():
        resp = await main.live_events_stream(_MockRequest())
        out = ""
        async for chunk in resp.body_iterator:
            out += chunk
            if "scrub_probe" in out:
                break
        return out

    body = asyncio.run(first_frames())
    assert "scrub_probe" in body
    assert "secret_url" not in body and "u:p@h" not in body
    assert '"data"' not in body


# ---------------------------------------------------------------------------
# Debug-event type derivation: the SDK labels any payload without 'label' or
# 'action' as "unknown" (web_mixin.py), and the platform's debug webhook
# payloads carry neither. The bus must derive a presentable type from the
# payload body so the Live Wire panel never shows bare "unknown" rows.
# ---------------------------------------------------------------------------

def test_derive_keeps_real_event_types():
    assert live_events.derive_event_type("step_change", {"step": "weather"}) == "step_change"


def test_derive_explicit_type_keys():
    assert live_events.derive_event_type("unknown", {"event_type": "ai_start"}) == "ai_start"
    assert live_events.derive_event_type("unknown", {"type": "utterance"}) == "utterance"
    assert live_events.derive_event_type(None, {"event": "barge"}) == "barge"


def test_derive_conversation_roles():
    assert live_events.derive_event_type("unknown", {"role": "assistant", "content": "Hi!"}) == "ai_response"
    assert live_events.derive_event_type("unknown", {"role": "user", "content": "joke please"}) == "caller_speech"
    assert live_events.derive_event_type("unknown", {"role": "tool", "content": "result"}) == "tool_result"


def test_derive_swaig_and_steps():
    assert live_events.derive_event_type("unknown", {"command_name": "get_weather"}) == "function:get_weather"
    assert live_events.derive_event_type("unknown", {"function_name": "tell_joke"}) == "function:tell_joke"
    assert live_events.derive_event_type("unknown", {"step_name": "menu"}) == "step_change"


def test_derive_alien_payload_names_its_key_instead_of_unknown():
    t = live_events.derive_event_type("unknown", {"call_id": "x", "barge_count": 2})
    assert t == "event:barge_count"


def test_derive_hopeless_payloads_stay_unknown():
    assert live_events.derive_event_type("unknown", {}) == "unknown"
    assert live_events.derive_event_type(None, "not a dict") == "unknown"


def test_emit_applies_derivation_and_summary_shows_content():
    bus = _fresh()
    bus.emit("ai", "unknown", {"role": "assistant", "content": "Here's a dad joke."})
    e = bus.since(0)[0]
    assert e["type"] == "ai_response"
    assert "unknown" not in e["summary"]
    assert "dad joke" in e["summary"]


# ---------------------------------------------------------------------------
# Real platform envelope (verified live 2026-06-11): every debug POST is
# {"call_info": {...routing metadata...}, "<event_name>": {...payload...}}.
# The event name is the sibling key of call_info; the inner dict is the data.
# ---------------------------------------------------------------------------

_CI = {"project_id": "p", "space_id": "s", "call_id": "c",
       "content_type": "text/json", "content_disposition": "post_data",
       "conversation_type": "voice"}


def test_derive_unwraps_call_info_envelope():
    assert live_events.derive_event_type(
        "unknown", {"call_info": _CI, "filler": {"text": "So", "filler_type": "thinking"}}) == "filler"
    assert live_events.derive_event_type(
        "unknown", {"call_info": _CI, "speech_detect": {"text": "joke", "source": "live"}}) == "speech_detect"
    assert live_events.derive_event_type(
        "unknown", {"call_info": _CI, "session_end": {"reason": "normal", "duration_ms": 19777}}) == "session_end"


def test_envelope_summary_includes_inner_payload():
    bus = _fresh()
    bus.emit("ai", "unknown", {"call_info": _CI,
                               "speech_detect": {"text": "tell me a joke", "source": "live"}})
    e = bus.since(0)[0]
    assert e["type"] == "speech_detect"
    assert "tell me a joke" in e["summary"]


def test_post_prompt_summary_never_leaks_token_url():
    bus = _fresh()
    bus.emit("ai", "unknown", {"call_info": _CI,
                               "post_prompt": {"url": "https://x/step11/post_prompt/?__token=SECRET"}})
    e = bus.since(0)[0]
    assert e["type"] == "post_prompt"
    assert "SECRET" not in e["summary"] and "__token" not in e["summary"]
