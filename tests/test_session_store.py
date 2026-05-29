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
