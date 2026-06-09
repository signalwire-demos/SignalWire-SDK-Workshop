from error_store import ErrorStore


def test_records_newest_first_and_caps(tmp_path):
    es = ErrorStore(path=str(tmp_path / "e.json"), cap=3)
    for i in range(5):
        es.record(source="swaig", message=f"err {i}", detail="trace")
    items = es.all()
    assert len(items) == 3                # capped
    assert items[0]["message"] == "err 4"  # newest first


def test_version_bumps_and_persists(tmp_path):
    p = str(tmp_path / "e.json")
    es = ErrorStore(path=p, cap=10)
    v0 = es.version
    es.record(source="post_prompt", message="bad json", detail="...")
    assert es.version > v0
    es2 = ErrorStore(path=p, cap=10)
    es2.load()
    assert es2.all()[0]["message"] == "bad json"
