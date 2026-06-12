# tests/test_swaig_admin_dispatch.py
"""The admin SWAIG tester must register every (route, function) pair, label
skills vs custom tools, and dispatch a test to the agent on the requested
route — not whichever agent happens to share the function name."""
import sys
sys.path.insert(0, ".")

import main  # noqa: E402  (builds + registers all agents; server.run() is guarded)


def _rows():
    return {(r["route"], r["name"]): r for r in main.function_health.STORE.all()}


def test_every_route_function_pair_is_registered():
    rows = _rows()
    # tell_joke is three different implementations on three routes (plus 08-10)
    for route in ("/step06", "/step07", "/step11"):
        assert (route, "tell_joke") in rows, route
    # get_weather is registered by steps 08 through 11
    for route in ("/step08", "/step09", "/step10", "/step11"):
        assert (route, "get_weather") in rows, route


def test_kinds_distinguish_skills_from_custom_tools():
    rows = _rows()
    assert rows[("/step06", "tell_joke")]["kind"] == "tool"
    assert rows[("/step11", "get_weather")]["kind"] == "tool"
    for route in ("/step10", "/step11"):
        assert rows[(route, "get_current_time")]["kind"] == "skill"
        assert rows[(route, "get_current_time")]["skill"] == "datetime"
        assert rows[(route, "get_current_date")]["skill"] == "datetime"
        assert rows[(route, "calculate")]["kind"] == "skill"
        assert rows[(route, "calculate")]["skill"] == "math"


def test_run_swaig_case_dispatches_to_requested_route(monkeypatch):
    # /step06 is the hardcoded joke list: offline and deterministic.
    v = main.run_swaig_case("tell_joke", route="/step06")
    assert v["ok"], v
    from python.steps.step06_hardcoded_jokes import JOKES
    assert any(j.lower() in v["result"].lower() for j in JOKES), v["result"]

    # /step07 is the live-API implementation: stub the network call and prove
    # THAT handler ran (the hardcoded list could never produce this joke).
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"joke": "Stubbed API joke from step07"}

    import python.steps.step07_api_jokes as step07
    monkeypatch.setattr(step07.requests, "get", lambda *a, **kw: _Resp())
    v = main.run_swaig_case("tell_joke", route="/step07")
    assert v["ok"], v
    assert "Stubbed API joke from step07" in v["result"]


def test_run_swaig_case_rejects_function_missing_on_route():
    v = main.run_swaig_case("get_weather", route="/step06")
    assert not v["ok"]
    assert "not registered" in v["result"]


def test_results_recorded_per_route(monkeypatch):
    main.run_swaig_case("tell_joke", route="/step06")
    rows = _rows()
    assert rows[("/step06", "tell_joke")]["status"] in ("ok", "failing")
    # the step07 row keeps its own status; running step06 must not touch it
    assert rows[("/step06", "tell_joke")]["last_run_at"] is not None
