"""Pluggable persistence backend for the workshop's JSON stores.

Each store mirrors its in-memory state to a single JSON blob via save()/load().
In dev/test that blob is a local file. On Replit the container filesystem is
rebuilt on every redeploy (wiping local files), so there the blob is persisted
to the Replit Key-Value DB via its REST API ($REPLIT_DB_URL), which survives
redeploys. The store logic is unchanged; only where the blob lives differs.

A backend exposes:
    read() -> str | None     # the persisted JSON blob, or None if absent
    write(blob: str) -> None # persist the blob; never raises (logs on failure)
"""
import os
import urllib.error
import urllib.parse
import urllib.request


class JsonFileBackend:
    """Persist a blob as a local file (dev/test default)."""

    def __init__(self, path):
        self._path = path

    def read(self):
        if not os.path.exists(self._path):
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            print(f"[storage] file read failed ({self._path}): {e}", flush=True)
            return None

    def write(self, blob):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(blob)
        except OSError as e:
            print(f"[storage] file write failed ({self._path}): {e}", flush=True)


class ReplitKVBackend:
    """Persist a blob under one key in the Replit Key-Value DB via its REST API.

    Survives redeploys (unlike the container filesystem). Uses stdlib urllib so
    no extra dependency is pulled in. Never raises: a transient KV error degrades
    to "not persisted" / "no data", matching the file backend's failure mode.
    """

    def __init__(self, key, db_url=None):
        self._key = key
        self._db_url = (db_url or os.environ.get("REPLIT_DB_URL") or "").rstrip("/")

    def read(self):
        if not self._db_url:
            return None
        url = f"{self._db_url}/{urllib.parse.quote(self._key, safe='')}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return body if body != "" else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"[storage] KV read failed ({self._key}): {e}", flush=True)
            return None
        except Exception as e:
            print(f"[storage] KV read failed ({self._key}): {e}", flush=True)
            return None

    def write(self, blob):
        if not self._db_url:
            return
        data = urllib.parse.urlencode({self._key: blob}).encode("utf-8")
        try:
            req = urllib.request.Request(self._db_url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as e:
            print(f"[storage] KV write failed ({self._key}): {e}", flush=True)


def resolve(path):
    """Pick a backend for a store identified by its local-file `path`.

    On Replit (REPLIT_DB_URL set) -> ReplitKVBackend keyed 'workshop:<stem>'
    (survives redeploys). Otherwise -> JsonFileBackend(path) for dev/test.
    Returns None for a falsy path (store persistence disabled, e.g. some tests).
    """
    if not path:
        return None
    if os.environ.get("REPLIT_DB_URL"):
        stem = os.path.basename(path)
        if stem.startswith(".workshop_"):
            stem = stem[len(".workshop_"):]
        if stem.endswith(".json"):
            stem = stem[: -len(".json")]
        return ReplitKVBackend(f"workshop:{stem}")
    return JsonFileBackend(path)
