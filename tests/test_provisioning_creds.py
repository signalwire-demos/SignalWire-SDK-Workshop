"""provisioning uses passed creds, not env, and operates on a passed setup dict."""
import python.provisioning as prov
import python.steps.step12_rest_demo as step12


class _FakeClient:
    def __init__(self, project, token, host):
        self.project, self.token, self.host = project, token, host
        self.phone_numbers = self
    def get(self, sid):  # phone_numbers.get
        return {"id": sid, "number": "+15551230000", "name": "X"}


def test_configure_existing_builds_client_from_passed_creds(monkeypatch):
    monkeypatch.setenv("SIGNALWIRE_PROJECT_ID", "WRONG")
    monkeypatch.setenv("SIGNALWIRE_TOKEN", "WRONG")
    monkeypatch.setenv("SIGNALWIRE_SPACE", "wrong.example.com")
    seen = {}
    def fake_sw_client(project, token, host):
        seen.update(project=project, token=token, host=host)
        return _FakeClient(project, token, host)
    monkeypatch.setattr(step12, "SignalWireClient", fake_sw_client)
    monkeypatch.setattr(prov, "step12", step12)  # ensure module ref
    monkeypatch.setattr(step12, "assign_number_to_agent", lambda *a, **k: {"resource_id": "r", "phone_route_id": "p"})

    creds = {"SIGNALWIRE_PROJECT_ID": "RIGHT", "SIGNALWIRE_TOKEN": "RT", "SIGNALWIRE_SPACE": "right.signalwire.com"}
    setup = prov.configure_existing(creds, "num-sid", "/step04", "https://x.example.com")

    assert seen["project"] == "RIGHT" and seen["host"] == "right.signalwire.com"
    assert setup["phone_number"] == "+15551230000" and setup["route"] == "/step04"


def test_setup_status_reports_creds_from_argument():
    s = prov.setup_status({"SIGNALWIRE_PROJECT_ID": "P", "SIGNALWIRE_TOKEN": "T", "SIGNALWIRE_SPACE": "s"}, {"phone_number": "+1"}, "https://x")
    assert s["creds_configured"] is True and s["setup"] == {"phone_number": "+1"}
