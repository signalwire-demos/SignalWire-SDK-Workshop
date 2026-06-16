from python.steps.step11_complete import _session_id_from_raw

def test_extracts_sid_from_global_data():
    assert _session_id_from_raw({"global_data": {"workshop_session_id": "S1"}}) == "S1"

def test_missing_returns_none():
    assert _session_id_from_raw({}) is None
    assert _session_id_from_raw({"global_data": {}}) is None
    assert _session_id_from_raw(None) is None
