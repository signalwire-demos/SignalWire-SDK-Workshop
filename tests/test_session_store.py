"""Unit tests for session_store."""
import os, time
import session_store as ss


def test_new_session_id_is_unique_and_long():
    a, b = ss.new_session_id(), ss.new_session_id()
    assert a != b and len(a) >= 32


def test_ensure_creates_empty_record_and_get_returns_it():
    store = ss.SessionStore(path=None)
    rec = store.ensure("sid1")
    assert rec["creds"] == {} and rec["setup"] == {} and rec["agent_address"] is None
    assert store.get("sid1") is rec


def test_get_unknown_returns_none():
    store = ss.SessionStore(path=None)
    assert store.get("nope") is None


def test_mutations_persist_through_save_and_load(tmp_path):
    p = tmp_path / "sessions.json"
    store = ss.SessionStore(path=str(p))
    rec = store.ensure("sid1")
    rec["creds"] = {"SIGNALWIRE_PROJECT_ID": "PX", "SIGNALWIRE_TOKEN": "PT", "SIGNALWIRE_SPACE": "demo.signalwire.com"}
    store.save()
    store2 = ss.SessionStore(path=str(p))
    store2.load()
    assert store2.get("sid1")["creds"]["SIGNALWIRE_PROJECT_ID"] == "PX"


def test_sweep_drops_only_idle_records():
    store = ss.SessionStore(path=None)
    fresh = store.ensure("fresh")
    old = store.ensure("old")
    old["last_seen"] = time.time() - 10_000
    store.sweep(ttl_seconds=3600)
    assert store.get("fresh") is fresh
    assert store.get("old") is None


def test_load_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "sessions.json"
    p.write_text("{not json")
    store = ss.SessionStore(path=str(p))
    store.load()
    assert store.get("anything") is None


def test_api_token_never_persisted_to_disk(tmp_path):
    # Replit publishing snapshots the whole project folder, gitignore or not,
    # and its security scan blocks the build when it finds a real token in
    # .workshop_sessions.json. The API token lives in memory only; the
    # project ID, space, and setup state still persist across restarts
    # (user decision 2026-06-11: keep project ID, never save the token).
    path = str(tmp_path / "sessions.json")
    s1 = ss.SessionStore(path=path)
    rec = s1.ensure("sid-1")
    rec["creds"] = {"SIGNALWIRE_PROJECT_ID": "px-1", "SIGNALWIRE_TOKEN": "PTsecret",
                    "SIGNALWIRE_SPACE": "demo.signalwire.com"}
    rec["setup"] = {"phone_number": "+13125550100", "route": "/step04"}
    s1.save()
    raw = open(path).read()
    assert "PTsecret" not in raw
    assert "px-1" in raw                  # project ID survives restarts
    assert "demo.signalwire.com" in raw   # space survives restarts
    assert "+13125550100" in raw          # setup state survives restarts

    s2 = ss.SessionStore(path=path)
    s2.load()
    rec2 = s2.get("sid-1")
    assert "SIGNALWIRE_TOKEN" not in rec2["creds"]
    assert rec2["creds"]["SIGNALWIRE_PROJECT_ID"] == "px-1"
    assert rec2["setup"]["phone_number"] == "+13125550100"
    # In-memory record is untouched: the live session keeps working.
    assert rec["creds"]["SIGNALWIRE_TOKEN"] == "PTsecret"


def test_load_scrubs_tokens_from_legacy_files(tmp_path):
    # Files written by older builds may already hold raw tokens; loading one
    # must drop them so the next save() leaves the file clean.
    import json
    path = str(tmp_path / "sessions.json")
    with open(path, "w") as f:
        json.dump({"old-sid": {"creds": {"SIGNALWIRE_TOKEN": "PTlegacy",
                                         "SIGNALWIRE_PROJECT_ID": "px-old"},
                               "setup": {}, "agent_address": None,
                               "signed_in_at": 1.0, "last_seen": 2.0}}, f)
    s = ss.SessionStore(path=path)
    s.load()
    assert "SIGNALWIRE_TOKEN" not in s.get("old-sid")["creds"]
    assert s.get("old-sid")["creds"]["SIGNALWIRE_PROJECT_ID"] == "px-old"
    s.save()
    assert "PTlegacy" not in open(path).read()
