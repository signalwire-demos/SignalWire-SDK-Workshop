# tests/test_store_persistence_kv.py
"""Stores must reload their state from the durable backend so /admin survives a
redeploy. Simulated by pointing two store instances at the same in-process KV
server (a redeploy = a fresh process reading the same KV)."""
import http.server
import os
import threading
import urllib.parse

import call_store
import session_store
import storage


class _KVHandler(http.server.BaseHTTPRequestHandler):
    store = {}
    def log_message(self, *a):
        pass
    def do_GET(self):
        key = urllib.parse.unquote(self.path.lstrip("/"))
        if key in self.store:
            self.send_response(200); self.end_headers()
            self.wfile.write(self.store[key].encode())
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items():
            self.store[k] = v[0]
        self.send_response(200); self.end_headers()


def _kv():
    _KVHandler.store = {}
    srv = http.server.HTTPServer(("127.0.0.1", 0), _KVHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_session_store_survives_redeploy(monkeypatch, tmp_path):
    srv, url = _kv()
    monkeypatch.setenv("REPLIT_DB_URL", url)
    # Use tmp_path so the test never touches real CWD files; the basename
    # ".workshop_sessions.json" still drives the KV key to "workshop:sessions".
    store_path = str(tmp_path / ".workshop_sessions.json")
    try:
        s1 = session_store.SessionStore(path=store_path)
        s1.ensure("sid-1")
        s1.mark_signed_in("sid-1")
        s1.save()

        # TRUE regression guard: KV backend must have received the blob.
        # Unwired code never calls _KVHandler, so its store stays empty.
        assert "workshop:sessions" in _KVHandler.store, (
            "KV backend was not written — store is not wired to ReplitKVBackend"
        )

        # KV path must not have created a local file.
        assert not os.path.exists(store_path), (
            "save() created a local file instead of using the KV backend"
        )

        s2 = session_store.SessionStore(path=store_path)
        s2.load()
        assert s2.get("sid-1") is not None
    finally:
        srv.shutdown()


def test_call_store_survives_redeploy(monkeypatch, tmp_path):
    srv, url = _kv()
    monkeypatch.setenv("REPLIT_DB_URL", url)
    # Use tmp_path so the test never touches real CWD files; the basename
    # ".workshop_calls.json" still drives the KV key to "workshop:calls".
    store_path = str(tmp_path / ".workshop_calls.json")
    try:
        c1 = call_store.CallStore(path=store_path)
        c1._calls = [{"call_id": "abc"}]; c1._ids = {"abc"}
        c1.save()

        # TRUE regression guard: KV backend must have received the blob.
        # Unwired code never calls _KVHandler, so its store stays empty.
        assert "workshop:calls" in _KVHandler.store, (
            "KV backend was not written — store is not wired to ReplitKVBackend"
        )

        # KV path must not have created a local file.
        assert not os.path.exists(store_path), (
            "save() created a local file instead of using the KV backend"
        )

        c2 = call_store.CallStore(path=store_path)
        c2.load()
        assert any(r.get("call_id") == "abc" for r in c2.all())
    finally:
        srv.shutdown()


def test_file_backend_still_works(tmp_path, monkeypatch):
    monkeypatch.delenv("REPLIT_DB_URL", raising=False)
    p = str(tmp_path / ".workshop_calls.json")
    c1 = call_store.CallStore(path=p)
    c1._calls = [{"call_id": "f1"}]; c1._ids = {"f1"}
    c1.save()
    c2 = call_store.CallStore(path=p)
    c2.load()
    assert any(r.get("call_id") == "f1" for r in c2.all())


import config_store
import error_store
import function_health


def test_config_store_survives_redeploy(monkeypatch, tmp_path):
    srv, url = _kv()
    monkeypatch.setenv("REPLIT_DB_URL", url)
    p = str(tmp_path / ".workshop_config.json")
    try:
        c1 = config_store.ConfigStore(path=p)
        c1.update(public_base="https://demo.example", auth_user="u", auth_password="p")
        assert "workshop:config" in _KVHandler.store      # proves KV was written
        assert not os.path.exists(p)                       # KV path, no disk file
        c2 = config_store.ConfigStore(path=p)
        c2.load()
        assert c2.effective_base() == "https://demo.example"
    finally:
        srv.shutdown()


def test_error_store_survives_redeploy(monkeypatch, tmp_path):
    srv, url = _kv()
    monkeypatch.setenv("REPLIT_DB_URL", url)
    p = str(tmp_path / ".workshop_errors.json")
    try:
        e1 = error_store.ErrorStore(path=p)
        e1.record("swaig", "boom")
        assert "workshop:errors" in _KVHandler.store
        assert not os.path.exists(p)
        e2 = error_store.ErrorStore(path=p)
        e2.load()
        assert any(i["message"] == "boom" for i in e2.all())
    finally:
        srv.shutdown()


def test_function_health_survives_redeploy(monkeypatch, tmp_path):
    srv, url = _kv()
    monkeypatch.setenv("REPLIT_DB_URL", url)
    p = str(tmp_path / ".workshop_function_health.json")
    try:
        f1 = function_health.FunctionHealth(path=p)
        f1.record_result("tell_joke", ok=True, route="/step11")
        assert "workshop:function_health" in _KVHandler.store
        assert not os.path.exists(p)
        f2 = function_health.FunctionHealth(path=p)
        f2.load()
        assert any(r["name"] == "tell_joke" and r["route"] == "/step11" for r in f2.all())
    finally:
        srv.shutdown()
