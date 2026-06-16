"""Thread-safe, JSON-persisted ring buffer of recent server errors for /admin.

Mirrors call_store.py's lock + version + persistence. Capped (newest-first) so
a long workshop can't grow it without bound.
"""
import json
import os
import threading
import time

import storage


class ErrorStore:
    def __init__(self, path=None, cap=200):
        self._path = path
        self._backend = storage.resolve(path)
        self._cap = cap
        self._items = []  # newest-first
        self._lock = threading.Lock()
        self.version = 0

    def record(self, source, message, detail=""):
        item = {
            "at": time.time(), "source": source,
            "message": str(message)[:300], "detail": str(detail)[:2000],
        }
        with self._lock:
            self._items.insert(0, item)
            del self._items[self._cap:]
            self.version += 1
        self.save()
        return item

    def all(self):
        with self._lock:
            return list(self._items)

    def clear(self):
        with self._lock:
            self._items = []
            self.version += 1
        self.save()

    def save(self):
        if not self._backend:
            return
        with self._lock:
            snapshot = json.dumps(self._items)
        self._backend.write(snapshot)

    def load(self):
        if not self._backend:
            return
        raw = self._backend.read()
        if raw is None:
            return
        try:
            data = json.loads(raw)
        except ValueError as e:
            print(f"[error_store] ignoring unreadable data: {e}", flush=True)
            return
        if isinstance(data, list):
            with self._lock:
                self._items = data[: self._cap]


STORE = ErrorStore(path=".workshop_errors.json")
STORE.load()
