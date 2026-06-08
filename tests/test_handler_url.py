"""The provisioned handler URL must carry the session id as ?sid=."""
from python.steps import step12_rest_demo as step12


def test_authed_url_appends_sid(monkeypatch):
    monkeypatch.setenv("SWML_BASIC_AUTH_USER", "workshop")
    monkeypatch.setenv("SWML_BASIC_AUTH_PASSWORD", "password")
    url = step12._authed_url("https://example.test", "/step11", sid="sess-xyz")
    assert url == "https://workshop:password@example.test/step11?sid=sess-xyz"


def test_authed_url_without_sid_has_no_query(monkeypatch):
    monkeypatch.setenv("SWML_BASIC_AUTH_USER", "workshop")
    monkeypatch.setenv("SWML_BASIC_AUTH_PASSWORD", "password")
    url = step12._authed_url("https://example.test", "/step11")
    assert url == "https://workshop:password@example.test/step11"
