"""Unit tests for the runtime ConfigStore (no server, no network)."""
import config_store


def _fresh(monkeypatch, tmp_path):
    for k in ("SWML_PROXY_URL_BASE", "SWML_BASIC_AUTH_USER", "SWML_BASIC_AUTH_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    return config_store.ConfigStore(path=str(tmp_path / "cfg.json"))


def test_effective_base_precedence(monkeypatch, tmp_path):
    c = _fresh(monkeypatch, tmp_path)
    # default fallback
    assert c.effective_base(env_default="https://startup") == "https://startup"
    # env beats startup default
    monkeypatch.setenv("SWML_PROXY_URL_BASE", "https://env")
    assert c.effective_base(env_default="https://startup") == "https://env"
    # detected beats env
    c.set_detected_base("https://detected.replit.app")
    assert c.effective_base(env_default="https://startup") == "https://detected.replit.app"
    # manual override beats everything
    c.update(public_base="https://override")
    assert c.effective_base(env_default="https://startup") == "https://override"


def test_effective_auth_defaults_then_override(monkeypatch, tmp_path):
    c = _fresh(monkeypatch, tmp_path)
    assert c.effective_auth() == ("workshop", "password")
    c.update(auth_user="alice", auth_password="s3cret")
    assert c.effective_auth() == ("alice", "s3cret")


def test_empty_string_clears_override(monkeypatch, tmp_path):
    c = _fresh(monkeypatch, tmp_path)
    c.update(public_base="https://override")
    assert c.effective_base(env_default="https://startup") == "https://override"
    c.update(public_base="")  # clear -> fall back to default
    assert c.effective_base(env_default="https://startup") == "https://startup"


def test_set_detected_base_change_detection(monkeypatch, tmp_path):
    c = _fresh(monkeypatch, tmp_path)
    assert c.set_detected_base("https://a.replit.app") is True
    assert c.set_detected_base("https://a.replit.app") is False  # unchanged
    assert c.set_detected_base("https://b.replit.app") is True


def test_persistence_round_trip(monkeypatch, tmp_path):
    path = str(tmp_path / "cfg.json")
    c1 = config_store.ConfigStore(path=path)
    c1.update(public_base="https://kept", auth_user="bob")
    c2 = config_store.ConfigStore(path=path)
    c2.load()
    monkeypatch.delenv("SWML_PROXY_URL_BASE", raising=False)
    assert c2.effective_base() == "https://kept"
    assert c2.effective_auth()[0] == "bob"


def test_snapshot_reports_source(monkeypatch, tmp_path):
    c = _fresh(monkeypatch, tmp_path)
    c.set_detected_base("https://detected.replit.app")
    snap = c.snapshot()
    assert snap["public_base"] == "https://detected.replit.app"
    assert snap["public_base_overridden"] is False
    c.update(public_base="https://override")
    assert c.snapshot()["public_base_overridden"] is True
