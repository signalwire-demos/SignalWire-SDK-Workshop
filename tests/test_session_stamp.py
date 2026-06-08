"""step11 stamps the workshop session id into global_data from the ?sid= param."""
from python.steps.step11_complete import CompleteAgent


class _FakeRequest:
    def __init__(self, sid=None):
        self.query_params = {"sid": sid} if sid else {}


def test_on_swml_request_stamps_session_id():
    agent = CompleteAgent(route="/step11")
    mods = agent.on_swml_request({"sid": "sess-xyz"}, None, _FakeRequest("sess-xyz"))
    assert mods["global_data"]["workshop_session_id"] == "sess-xyz"


def test_on_swml_request_no_sid_returns_no_stamp():
    agent = CompleteAgent(route="/step11")
    mods = agent.on_swml_request({}, None, _FakeRequest())
    assert not (mods or {}).get("global_data", {}).get("workshop_session_id")
