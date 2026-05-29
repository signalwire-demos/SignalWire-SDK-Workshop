"""Per-session state for the multi-tenant workshop.

Each browser gets a random session id (httpOnly cookie). Its SignalWire
credentials, provisioned-number record, and resolved agent address live here,
isolated from every other browser. Persisted to a private-disk JSON so a server
restart does not log everyone out. Thread-safe for uvicorn's worker threads.
"""
import json
import os
import secrets
import threading
import time

DEFAULT_TTL_SECONDS = 12 * 60 * 60


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _empty_record() -> dict:
    return {"creds": {}, "setup": {}, "agent_address": None, "last_seen": time.time()}


class SessionStore:
    def __init__(self, path=None):
        self._path = path
        self._sessions = {}
        self._lock = threading.Lock()

    def get(self, session_id):
        with self._lock:
            return self._sessions.get(session_id)

    def ensure(self, session_id) -> dict:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                rec = _empty_record()
                self._sessions[session_id] = rec
            rec["last_seen"] = time.time()
            return rec

    def touch(self, session_id):
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is not None:
                rec["last_seen"] = time.time()

    def sweep(self, ttl_seconds=DEFAULT_TTL_SECONDS):
        cutoff = time.time() - ttl_seconds
        with self._lock:
            for sid in [s for s, r in self._sessions.items() if r.get("last_seen", 0) < cutoff]:
                self._sessions.pop(sid, None)

    def save(self):
        if not self._path:
            return
        with self._lock:
            snapshot = json.dumps(self._sessions)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(snapshot)
        except OSError as e:
            print(f"[session_store] save failed: {e}", flush=True)

    def load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[session_store] ignoring unreadable sessions file: {e}", flush=True)
            return
        if isinstance(data, dict):
            with self._lock:
                self._sessions = data
