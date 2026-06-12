"""Normalize and verify attendee-entered SignalWire credentials.

Attendees paste their Space URL in every shape the dashboard shows it:
'https://demo.signalwire.com', with a trailing slash, with a path, uppercase,
or just the bare space name. Every consumer (guest-token minting, the SDK REST
client) needs the bare API host, so all credential intake funnels through
normalize_creds() before storage.
"""
import re

SPACE_HELP = ("Enter your Space URL as it appears in your dashboard, like "
              "'demo.signalwire.com' (the https:// prefix is fine too).")

_HOST_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def normalize_space(raw) -> str:
    """Reduce any pasted Space URL form to the bare API host.

    Raises ValueError with an attendee-facing message (the wizard shows it
    verbatim) when the value cannot be a space host.
    """
    value = str(raw or "").strip().lower()
    # Scheme or protocol-relative prefix: keep only what follows.
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value)
    if value.startswith("//"):  # protocol-relative form
        value = value[2:]
    # Path, query, or fragment: the host is everything before the first one.
    value = re.split(r"[/?#]", value, 1)[0]
    value = value.split(":", 1)[0]  # port
    value = value.rstrip(".")
    if value and "." not in value:
        # Bare space name ('demo') — complete it to the API host.
        value = f"{value}.signalwire.com"
    if not _HOST_RE.match(value):
        raise ValueError(f"'{raw}' does not look like a SignalWire Space. {SPACE_HELP}")
    return value


def normalize_creds(creds: dict):
    """Return (normalized copy, list of human-readable change notes).

    Change notes are for server logs; they never include the token value.
    """
    normalized = {}
    changes = []
    for key, raw in creds.items():
        value = str(raw or "").strip()
        if key == "SIGNALWIRE_SPACE" and value:
            value = normalize_space(value)
            if value != str(raw):
                changes.append(f"SIGNALWIRE_SPACE normalized: '{raw}' -> '{value}'")
        elif value != raw:
            changes.append(f"{key}: stripped surrounding whitespace")
        normalized[key] = value
    return normalized, changes
