"""Per-session state for the multi-tenant workshop.

Each browser gets a random session id (httpOnly cookie). Its SignalWire
credentials, provisioned-number record, and resolved agent address live here,
isolated from every other browser. Persisted to a private-disk JSON so a server
restart does not log everyone out. Thread-safe for uvicorn's worker threads.
"""
import json
import secrets
import threading
import time

import storage

DEFAULT_TTL_SECONDS = 12 * 60 * 60


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _empty_record() -> dict:
    return {"creds": {}, "setup": {}, "agent_address": None,
            "signed_in_at": None, "last_seen": time.time()}


class SessionStore:
    def __init__(self, path=None):
        self._path = path
        self._backend = storage.resolve(path)
        self._sessions = {}
        self._lock = threading.Lock()
        self.version = 0

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

    def mark_signed_in(self, session_id):
        """Stamp the first successful credential sign-in. Idempotent."""
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return
            if rec.get("signed_in_at") is None:
                rec["signed_in_at"] = time.time()
                self.version += 1

    def admin_snapshot(self):
        """Sanitized view of all sessions for the admin dashboard.

        The raw SIGNALWIRE_TOKEN is NEVER included — only a masked tail.
        """
        def mask(tok):
            if not tok:
                return ""
            tail = tok[-4:] if len(tok) > 4 else ""
            return "•" * 6 + tail

        with self._lock:
            rows = []
            for sid, rec in self._sessions.items():
                creds = rec.get("creds", {})
                rows.append({
                    "session_id": sid,
                    "space": creds.get("SIGNALWIRE_SPACE"),
                    "project_id": creds.get("SIGNALWIRE_PROJECT_ID"),
                    "token_masked": mask(creds.get("SIGNALWIRE_TOKEN")),
                    "signed_in_at": rec.get("signed_in_at"),
                    "last_seen": rec.get("last_seen"),
                    "agent_address": rec.get("agent_address"),
                })
            return rows

    def sweep(self, ttl_seconds=DEFAULT_TTL_SECONDS):
        cutoff = time.time() - ttl_seconds
        with self._lock:
            for sid in [s for s, r in self._sessions.items() if r.get("last_seen", 0) < cutoff]:
                self._sessions.pop(sid, None)

    @staticmethod
    def _strip_token(rec):
        """Copy of a session record without the API token.

        Replit publishing snapshots the whole project folder (gitignore
        does not apply), and its security scan blocks the build if a real
        token sits in .workshop_sessions.json. Project ID, space, and setup
        state are fine to keep; only the token is a secret.
        """
        creds = {k: v for k, v in rec.get("creds", {}).items()
                 if k != "SIGNALWIRE_TOKEN"}
        return {**rec, "creds": creds}

    def save(self):
        if not self._backend:
            return
        with self._lock:
            snapshot = json.dumps({sid: self._strip_token(rec)
                                   for sid, rec in self._sessions.items()})
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
            print(f"[session_store] ignoring unreadable sessions data: {e}", flush=True)
            return
        if isinstance(data, dict):
            with self._lock:
                # _strip_token also scrubs tokens from data written by older
                # builds, so a poisoned blob self-cleans on boot.
                self._sessions = {sid: self._strip_token(rec)
                                  for sid, rec in data.items()
                                  if isinstance(rec, dict)}
