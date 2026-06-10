import importlib
from unittest import mock
from fastapi.testclient import TestClient


def test_mint_guest_token_posts_scoped_request():
    mod = importlib.import_module("python.steps.step12_rest_demo")
    creds = {
        "SIGNALWIRE_PROJECT_ID": "proj-123",
        "SIGNALWIRE_TOKEN": "tok-abc",
        "SIGNALWIRE_SPACE": "example.signalwire.com",
    }
    fake_resp = mock.Mock()
    fake_resp.json.return_value = {"token": "guest-xyz"}
    fake_resp.raise_for_status.return_value = None

    with mock.patch.object(mod.requests, "post", return_value=fake_resp) as post:
        token = mod.mint_guest_token("addr-uuid-1", creds=creds)

    assert token == "guest-xyz"
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://example.signalwire.com/api/fabric/guests/tokens"
    assert kwargs["json"]["allowed_addresses"] == ["addr-uuid-1"]
    assert "expire_at" in kwargs["json"]
    assert kwargs["auth"] == ("proj-123", "tok-abc")


def test_relay_config_uses_guest_token(monkeypatch):
    import main
    monkeypatch.setattr(main, "creds_for", lambda req: {
        "SIGNALWIRE_PROJECT_ID": "p", "SIGNALWIRE_TOKEN": "t", "SIGNALWIRE_SPACE": "x.signalwire.com",
    })
    import python.steps.step12_rest_demo as step12
    monkeypatch.setattr(step12, "ensure_agent_handler", lambda *a, **k: "buddy@x.signalwire.com")
    monkeypatch.setattr(step12, "agent_address_id", lambda *a, **k: "addr-uuid-1")
    monkeypatch.setattr(step12, "mint_guest_token", lambda *a, **k: "guest-xyz")

    client = TestClient(main.server.app)
    r = client.get("/api/relay/config")
    assert r.status_code == 200
    body = r.json()
    assert body["token"] == "guest-xyz"
    assert body["destination"] == "buddy@x.signalwire.com"


def test_agent_address_id_raises_on_empty_addresses():
    import pytest
    mod = importlib.import_module("python.steps.step12_rest_demo")
    fake_client = mock.Mock()
    fake_client.fabric.swml_webhooks.list_addresses.return_value = {"data": []}
    with mock.patch.object(mod, "_find_swml_webhook", return_value=("res-id", "http://x")):
        with pytest.raises(RuntimeError, match="no addresses"):
            mod.agent_address_id(client=fake_client)
