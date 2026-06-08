"""Correlation prefers global_data.workshop_session_id, falls back to phone.

`import main` triggers server.run() which would bind a port, so we patch
AgentServer.run to a no-op before the import — mirroring how other unit tests
avoid starting the full server.
"""
import sys

import pytest


def _import_main():
    """Import main with server.run() patched out so no port is bound."""
    if "main" in sys.modules:
        return sys.modules["main"]
    from signalwire_agents import AgentServer
    original_run = AgentServer.run

    def noop_run(self, *a, **kw):
        pass

    AgentServer.run = noop_run
    try:
        import main  # noqa: PLC0415
    finally:
        AgentServer.run = original_run
    return main


main = _import_main()


def test_resolver_prefers_global_data():
    sess = main._SESSIONS
    sess.ensure("corr-1")
    rec = sess.get("corr-1")
    rec["creds"] = {"SIGNALWIRE_PROJECT_ID": "PX-corr",
                    "SIGNALWIRE_SPACE": "corr.signalwire.com"}
    out = main._resolve_session_for_call(
        {"global_data": {"workshop_session_id": "corr-1"}}
    )
    assert out["session_id"] == "corr-1"
    assert out["project_id"] == "PX-corr"


def test_resolver_matches_by_project_id():
    """Real payloads carry top-level project_id; correlate by it (the workhorse)."""
    sess = main._SESSIONS
    # Unique, test-only project id so it never collides with a persisted session.
    pid = "PX-corr-pid-unit-test-only"
    sess.ensure("corr-pid")
    sess.get("corr-pid")["creds"] = {
        "SIGNALWIRE_PROJECT_ID": pid,
        "SIGNALWIRE_SPACE": "pid.signalwire.com",
    }
    out = main._resolve_session_for_call({"project_id": pid})
    assert out["session_id"] == "corr-pid"
    assert out["project_id"] == pid


def test_resolver_unknown_session_returns_none():
    out = main._resolve_session_for_call(
        {"global_data": {"workshop_session_id": "does-not-exist"},
         "project_id": "no-such-project"}
    )
    assert out is None
