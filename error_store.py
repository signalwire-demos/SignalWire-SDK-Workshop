"""Thread-safe, JSON-persisted ring buffer of recent server errors for /admin.

Mirrors call_store.py's lock + version + persistence. Capped (newest-first) so
a long workshop can't grow it without bound.
"""
import json
import os
import threading
import time


class ErrorStore:
    def __init__(self, path=None, cap=200):
        self._path = path
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
        if not self._path:
            return
        with self._lock:
            snapshot = json.dumps(self._items)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(snapshot)
        except OSError as e:
            print(f"[error_store] save failed: {e}", flush=True)

    def load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[error_store] ignoring unreadable file: {e}", flush=True)
            return
        if isinstance(data, list):
            with self._lock:
                self._items = data[: self._cap]


STORE = ErrorStore(path=".workshop_errors.json")
STORE.load()
