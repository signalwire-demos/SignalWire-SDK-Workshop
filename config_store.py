"""Runtime app configuration, editable from the admin dashboard.

Three values that previously required Replit Secrets are managed here at runtime
instead, so a workshop host can fill them in on the /admin page:

- public_base   : the public URL SignalWire calls back (SWML / SWAIG / post_prompt).
                  Auto-detected from the incoming request host; overridable.
- auth_user     : HTTP basic-auth username embedded in provisioned webhook URLs
- auth_password : ...and validated on inbound SignalWire requests.

Overrides are JSON-persisted (mirrors session_store.py) so edits survive a
restart. `effective_*` merges: manual override -> auto-detected -> env -> default.
"""
import json
import os
import threading

DEFAULT_AUTH_USER = "workshop"
DEFAULT_AUTH_PASSWORD = "password"


class ConfigStore:
    def __init__(self, path=None):
        self._path = path
        self._lock = threading.Lock()
        # None means "not overridden" -> fall through to detected/env/default.
        self._data = {
            "public_base": None,     # manual override
            "detected_base": None,   # auto-detected from a real request host
            "auth_user": None,
            "auth_password": None,
        }

    # ----- persistence -----
    def load(self):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[config_store] ignoring unreadable config: {e}", flush=True)
            return
        if isinstance(data, dict):
            with self._lock:
                for k in self._data:
                    if k in data:
                        self._data[k] = data[k]

    def save(self):
        if not self._path:
            return
        with self._lock:
            snapshot = json.dumps(self._data)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(snapshot)
        except OSError as e:
            print(f"[config_store] save failed: {e}", flush=True)

    # ----- auto-detection -----
    def set_detected_base(self, base):
        """Record the public base seen on a real request. Returns True if changed."""
        with self._lock:
            if not base or self._data.get("detected_base") == base:
                return False
            self._data["detected_base"] = base
        self.save()
        return True

    # ----- overrides -----
    def update(self, public_base=None, auth_user=None, auth_password=None):
        """Set manual overrides. Pass a value to set it; pass "" to clear the
        override (fall back to detected/env/default); pass None to leave unchanged.
        """
        with self._lock:
            for key, val in (("public_base", public_base),
                             ("auth_user", auth_user),
                             ("auth_password", auth_password)):
                if val is None:
                    continue
                self._data[key] = (val.strip() or None) if isinstance(val, str) else val
        self.save()

    # ----- effective values -----
    def effective_base(self, env_default=None):
        with self._lock:
            override = self._data.get("public_base")
            detected = self._data.get("detected_base")
        return override or detected or os.environ.get("SWML_PROXY_URL_BASE") or env_default

    def effective_auth(self):
        with self._lock:
            user = self._data.get("auth_user")
            pw = self._data.get("auth_password")
        user = user or os.environ.get("SWML_BASIC_AUTH_USER") or DEFAULT_AUTH_USER
        pw = pw or os.environ.get("SWML_BASIC_AUTH_PASSWORD") or DEFAULT_AUTH_PASSWORD
        return user, pw

    def snapshot(self, env_default=None):
        """Sanitized view for the admin UI."""
        with self._lock:
            override = self._data.get("public_base")
            detected = self._data.get("detected_base")
        user, pw = self.effective_auth()
        return {
            "public_base": override or detected or os.environ.get("SWML_PROXY_URL_BASE") or env_default or "",
            "public_base_overridden": bool(override),
            "public_base_detected": detected or "",
            "auth_user": user,
            "auth_password": pw,
        }
