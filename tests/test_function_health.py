from function_health import FunctionHealth


def test_starts_untested_and_records_results(tmp_path):
    fh = FunctionHealth(path=str(tmp_path / "h.json"))
    fh.register("tell_joke", route="/step06", kind="tool")
    snap = {f["name"]: f for f in fh.all()}
    assert snap["tell_joke"]["status"] == "untested"

    fh.record_result("tell_joke", ok=True, detail="Here's a joke", latency_ms=12)
    assert {f["name"]: f for f in fh.all()}["tell_joke"]["status"] == "ok"

    fh.record_result("tell_joke", ok=False, detail="boom", latency_ms=5)
    assert {f["name"]: f for f in fh.all()}["tell_joke"]["status"] == "failing"


def test_version_bumps_and_persists(tmp_path):
    p = str(tmp_path / "h.json")
    fh = FunctionHealth(path=p)
    fh.register("get_weather", route="/step08", kind="datamap")
    v0 = fh.version
    fh.record_result("get_weather", ok=True, detail="Weather in Chicago", latency_ms=30)
    assert fh.version > v0

    fh2 = FunctionHealth(path=p)
    fh2.load()
    assert {f["name"]: f for f in fh2.all()}["get_weather"]["status"] == "ok"
