from function_health import FunctionHealth


def test_starts_untested_and_records_results(tmp_path):
    fh = FunctionHealth(path=str(tmp_path / "h.json"))
    fh.register("tell_joke", route="/step06", kind="tool")
    snap = {f["name"]: f for f in fh.all()}
    assert snap["tell_joke"]["status"] == "untested"

    fh.record_result("tell_joke", ok=True, detail="Here's a joke", latency_ms=12, route="/step06")
    assert {f["name"]: f for f in fh.all()}["tell_joke"]["status"] == "ok"

    fh.record_result("tell_joke", ok=False, detail="boom", latency_ms=5, route="/step06")
    assert {f["name"]: f for f in fh.all()}["tell_joke"]["status"] == "failing"


def test_version_bumps_and_persists(tmp_path):
    p = str(tmp_path / "h.json")
    fh = FunctionHealth(path=p)
    fh.register("get_weather", route="/step08", kind="tool")
    v0 = fh.version
    fh.record_result("get_weather", ok=True, detail="Weather in Chicago", latency_ms=30, route="/step08")
    assert fh.version > v0

    fh2 = FunctionHealth(path=p)
    fh2.load()
    assert {f["name"]: f for f in fh2.all()}["get_weather"]["status"] == "ok"


def test_same_name_on_two_routes_is_two_records(tmp_path):
    # tell_joke exists on /step06 (hardcoded) AND /step07 (live API): each
    # implementation must have its own health row, route, and test result.
    fh = FunctionHealth(path=str(tmp_path / "h.json"))
    fh.register("tell_joke", route="/step06", kind="tool")
    fh.register("tell_joke", route="/step07", kind="tool")
    rows = fh.all()
    assert len(rows) == 2
    assert {r["route"] for r in rows} == {"/step06", "/step07"}

    fh.record_result("tell_joke", ok=False, detail="api down", latency_ms=9, route="/step07")
    by_route = {r["route"]: r for r in fh.all()}
    assert by_route["/step07"]["status"] == "failing"
    assert by_route["/step06"]["status"] == "untested"  # unaffected


def test_register_keeps_skill_attribution(tmp_path):
    fh = FunctionHealth(path=str(tmp_path / "h.json"))
    fh.register("get_current_time", route="/step10", kind="skill", skill="datetime")
    fh.register("tell_joke", route="/step06", kind="tool")
    rows = {(r["route"], r["name"]): r for r in fh.all()}
    assert rows[("/step10", "get_current_time")]["kind"] == "skill"
    assert rows[("/step10", "get_current_time")]["skill"] == "datetime"
    assert rows[("/step06", "tell_joke")]["kind"] == "tool"
    assert rows[("/step06", "tell_joke")]["skill"] is None


def test_load_drops_legacy_name_keyed_records(tmp_path):
    # Pre-route-keying files have records without a "route"; replaying them
    # would resurrect the old collapsed rows next to the new per-route ones.
    p = tmp_path / "h.json"
    p.write_text('[{"name": "tell_joke", "kind": "tool", "status": "ok"}]')
    fh = FunctionHealth(path=str(p))
    fh.load()
    assert fh.all() == []
