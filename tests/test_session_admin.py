import json

import session_store


def test_mark_signed_in_stamps_once():
    store = session_store.SessionStore()
    store.ensure("s1")
    store.mark_signed_in("s1")
    first = store.get("s1")["signed_in_at"]
    assert first is not None
    store.mark_signed_in("s1")                 # idempotent
    assert store.get("s1")["signed_in_at"] == first


def test_admin_snapshot_masks_token():
    store = session_store.SessionStore()
    rec = store.ensure("s1")
    rec["creds"] = {
        "SIGNALWIRE_PROJECT_ID": "PX-1234",
        "SIGNALWIRE_TOKEN": "PT-supersecret-value",
        "SIGNALWIRE_SPACE": "demo.signalwire.com",
    }
    store.mark_signed_in("s1")
    snap = store.admin_snapshot()
    assert len(snap) == 1
    row = snap[0]
    assert row["project_id"] == "PX-1234"
    assert row["space"] == "demo.signalwire.com"
    assert "supersecret" not in row["token_masked"]
    assert row["token_masked"].endswith("alue") or row["token_masked"].endswith("•")
    assert "SIGNALWIRE_TOKEN" not in json.dumps(snap)   # raw token never leaks


def test_version_increments_on_sign_in():
    store = session_store.SessionStore()
    store.ensure("s1")
    v = store.version
    store.mark_signed_in("s1")
    assert store.version == v + 1
