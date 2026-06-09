"""Thread-safe, JSON-persisted health state for each SWAIG function.

Mirrors call_store.py: a lock-guarded dict + a monotonically increasing
version counter the /admin SSE stream polls, plus best-effort JSON persistence.
"""
import json
import os
import threading
import time


class FunctionHealth:
    def __init__(self, path=None):
        self._path = path
        self._fns = {}  # name -> record
        self._lock = threading.Lock()
        self.version = 0

    def register(self, name, route=None, kind="tool"):
        with self._lock:
            rec = self._fns.get(name)
            if rec is None:
                self._fns[name] = {
                    "name": name, "route": route, "kind": kind,
                    "status": "untested", "last_detail": "", "last_latency_ms": None,
                    "last_run_at": None,
                }
                self.version += 1
            else:
                rec["route"] = route or rec["route"]
                rec["kind"] = kind or rec["kind"]

    def record_result(self, name, ok, detail="", latency_ms=None):
        with self._lock:
            rec = self._fns.setdefault(name, {"name": name, "route": None, "kind": "tool"})
            rec["status"] = "ok" if ok else "failing"
            rec["last_detail"] = (detail or "")[:500]
            rec["last_latency_ms"] = latency_ms
            rec["last_run_at"] = time.time()
            self.version += 1
        self.save()

    def all(self):
        with self._lock:
            return [dict(v) for v in self._fns.values()]

    def save(self):
        if not self._path:
            return
        with self._lock:
            snapshot = json.dumps(list(self._fns.values()))
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(snapshot)
        except OSError as e:
            print(f"[function_health] save failed: {e}", flush=True)

    def load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[function_health] ignoring unreadable file: {e}", flush=True)
            return
        if isinstance(data, list):
            with self._lock:
                self._fns = {r["name"]: r for r in data if "name" in r}


STORE = FunctionHealth(path=".workshop_function_health.json")
STORE.load()
