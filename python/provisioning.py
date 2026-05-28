"""
Workshop provisioning — does the manual SignalWire dashboard setup for the
attendee, end-to-end, via the SignalWire REST API.

Two surfaces of the same REST API, same (project, token) credentials:
  - LaML REST via signalwire.rest.Client  (phone number search/buy/update)
  - Fabric REST via raw HTTPS              (external_swml_handler resource)

The current state of the workshop (selected phone number + handler id) is
persisted to a small JSON file so a server restart does not lose the user's
purchased number.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

from signalwire.rest import Client as RestClient

from python.steps.step12_rest_demo import (
    HANDLER_NAME,
    DEFAULT_AGENT_PATH,
    ensure_agent_handler,
    _public_base,
)

FRIENDLY_NAME = "Chicago Roadshow 2026 — Buddy"

_SETUP_FILE = pathlib.Path(__file__).resolve().parent.parent / ".workshop_setup.json"


def _creds():
    try:
        return (
            os.environ["SIGNALWIRE_PROJECT_ID"],
            os.environ["SIGNALWIRE_TOKEN"],
            os.environ["SIGNALWIRE_SPACE"],
        )
    except KeyError as missing:
        raise RuntimeError(f"missing required env var: {missing.args[0]}") from None


def _client() -> RestClient:
    project, token, space = _creds()
    return RestClient(project, token, signalwire_space_url=space)


def load_setup() -> dict:
    try:
        return json.loads(_SETUP_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_setup(data: dict) -> None:
    _SETUP_FILE.write_text(json.dumps(data, indent=2))


def clear_setup() -> None:
    try:
        _SETUP_FILE.unlink()
    except FileNotFoundError:
        pass


def list_existing_numbers(limit: int = 3) -> list[dict]:
    """Return up to `limit` IncomingPhoneNumber records already on the project."""
    client = _client()
    out = []
    for num in client.incoming_phone_numbers.list(limit=limit):
        out.append({
            "sid": num.sid,
            "phone_number": num.phone_number,
            "friendly_name": num.friendly_name,
            "voice_url": num.voice_url or "",
        })
    return out


def search_available(area_code: Optional[str] = None, limit: int = 3) -> list[dict]:
    """Search US local numbers; optionally filter by area code."""
    client = _client()
    kwargs = {"limit": limit}
    if area_code:
        kwargs["area_code"] = int(area_code)
    nums = client.available_phone_numbers("US").local.list(**kwargs)
    return [
        {
            "phone_number": n.phone_number,
            "friendly_name": n.friendly_name,
            "locality": getattr(n, "locality", "") or "",
            "region": getattr(n, "region", "") or "",
        }
        for n in nums
    ]


def configure_existing(sid: str, route: str, public_base: str) -> dict:
    """Repoint an existing number's voice_url at `route`. Also sync the Fabric handler."""
    target_url = f"{public_base.rstrip('/')}{route}"
    client = _client()
    updated = client.incoming_phone_numbers(sid).update(voice_url=target_url)
    ensure_agent_handler(public_base=public_base, route=route)
    setup = {
        "sid": updated.sid,
        "phone_number": updated.phone_number,
        "friendly_name": updated.friendly_name,
        "voice_url": updated.voice_url,
        "route": route,
        "source": "existing",
    }
    save_setup(setup)
    return setup


def purchase_and_configure(phone_number: str, route: str, public_base: str) -> dict:
    """Buy `phone_number` on the project, set voice_url to `route`, sync handler."""
    target_url = f"{public_base.rstrip('/')}{route}"
    client = _client()
    bought = client.incoming_phone_numbers.create(
        phone_number=phone_number,
        voice_url=target_url,
        friendly_name=FRIENDLY_NAME,
    )
    ensure_agent_handler(public_base=public_base, route=route)
    setup = {
        "sid": bought.sid,
        "phone_number": bought.phone_number,
        "friendly_name": bought.friendly_name,
        "voice_url": bought.voice_url,
        "route": route,
        "source": "purchased",
    }
    save_setup(setup)
    return setup


def repoint_to_route(route: str, public_base: str) -> dict:
    """Update the saved number's voice_url + Fabric handler primary_request_url to `route`."""
    setup = load_setup()
    sid = setup.get("sid")
    if not sid:
        raise RuntimeError("no provisioned number; run setup first")
    target_url = f"{public_base.rstrip('/')}{route}"
    client = _client()
    updated = client.incoming_phone_numbers(sid).update(voice_url=target_url)
    ensure_agent_handler(public_base=public_base, route=route)
    setup.update({
        "voice_url": updated.voice_url,
        "route": route,
    })
    save_setup(setup)
    return setup


def setup_status(public_base: str) -> dict:
    """Return current persisted setup + cred status."""
    creds_ok = all(os.environ.get(k) for k in (
        "SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE",
    ))
    return {
        "creds_configured": creds_ok,
        "public_base": public_base or "",
        "setup": load_setup(),
        "default_route": DEFAULT_AGENT_PATH,
        "handler_name": HANDLER_NAME,
        "friendly_name": FRIENDLY_NAME,
    }
