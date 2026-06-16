"""Pluggable persistence backend. JsonFileBackend keeps dev/test on local files;
ReplitKVBackend persists to the Replit Key-Value DB REST API so /admin data
survives redeploys. resolve() picks KV when REPLIT_DB_URL is set."""
import http.server
import threading
import urllib.parse

import storage


def test_json_file_backend_round_trip(tmp_path):
    b = storage.JsonFileBackend(str(tmp_path / "x.json"))
    assert b.read() is None           # absent -> None
    b.write('{"a": 1}')
    assert b.read() == '{"a": 1}'


def test_resolve_uses_file_without_replit(monkeypatch):
    monkeypatch.delenv("REPLIT_DB_URL", raising=False)
    b = storage.resolve(".workshop_calls.json")
    assert isinstance(b, storage.JsonFileBackend)


def test_resolve_uses_kv_on_replit(monkeypatch):
    monkeypatch.setenv("REPLIT_DB_URL", "https://kv.example/db")
    b = storage.resolve(".workshop_calls.json")
    assert isinstance(b, storage.ReplitKVBackend)
    assert b._key == "workshop:calls"


class _KVHandler(http.server.BaseHTTPRequestHandler):
    store = {}
    def log_message(self, *a):           # silence test server
        pass
    def do_GET(self):
        key = urllib.parse.unquote(self.path.lstrip("/"))
        if key in self.store:
            body = self.store[key].encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        for k, v in form.items():
            self.store[k] = v[0]
        self.send_response(200); self.end_headers()


def _kv_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _KVHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_replit_kv_backend_round_trip():
    _KVHandler.store = {}
    srv, url = _kv_server()
    try:
        b = storage.ReplitKVBackend("workshop:calls", db_url=url)
        assert b.read() is None                  # missing key -> None
        b.write('[{"call_id": "c1"}]')
        assert b.read() == '[{"call_id": "c1"}]'
    finally:
        srv.shutdown()


def test_replit_kv_backend_never_raises_on_bad_url():
    b = storage.ReplitKVBackend("workshop:calls", db_url="http://127.0.0.1:1")  # nothing listening
    assert b.read() is None       # degrades to "no data"
    b.write("ignored")            # degrades to "not persisted"; must not raise
