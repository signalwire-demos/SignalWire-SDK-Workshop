"""
Workshop provisioning — does the SignalWire dashboard setup for the attendee,
end-to-end, via the SignalWire REST API (the agents-SDK Fabric/Relay client).

Everything goes through signalwire_agents.rest.client.SignalWireClient:
  - phone number search / buy / list / get   (Relay REST: client.phone_numbers)
  - SWML webhook resource + phone-route assignment (Fabric REST: client.fabric)

The current state of the workshop (selected phone number + handler id) is
persisted to a small JSON file so a server restart does not lose the user's
purchased number.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Optional

from python.steps.step12_rest_demo import (
    HANDLER_NAME,
    DEFAULT_AGENT_PATH,
    assign_number_to_agent,
    _client,
)

FRIENDLY_NAME = "Chicago Roadshow 2026 — Buddy"

_SETUP_FILE = pathlib.Path(__file__).resolve().parent.parent / ".workshop_setup.json"


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
    """Return up to `limit` phone numbers already on the project (Relay REST)."""
    client = _client()
    listing = client.phone_numbers.list(page_size=limit)
    return [
        {
            "sid": num.get("id"),
            "phone_number": num.get("number"),
            "friendly_name": num.get("name") or "",
        }
        for num in listing.get("data", [])
    ]


def search_available(area_code: Optional[str] = None, limit: int = 3) -> list[dict]:
    """Search US local numbers (Relay REST); optionally filter by area code."""
    client = _client()
    params = {"number_type": "local", "max_results": limit}
    if area_code:
        params["areacode"] = area_code
    found = client.phone_numbers.search(**params)
    return [
        {
            "phone_number": n.get("number"),
            "friendly_name": "",
            "locality": n.get("city") or "",
            "region": n.get("region") or "",
        }
        for n in found.get("data", [])
    ]


def _timed(api: str, op: str, fn, trace: list):
    """Run fn(), append {api, op, ms} to trace. Returns fn's return value."""
    t0 = time.monotonic()
    try:
        return fn()
    finally:
        trace.append({"api": api, "op": op, "ms": int((time.monotonic() - t0) * 1000)})


def configure_existing(sid: str, route: str, public_base: str) -> dict:
    """Assign an existing number (by id) to the agent's SWML webhook for `route`."""
    client = _client()
    # Provisioning goes through the SWML webhook + Fabric assignment (the fix
    # branch dropped the LaML compatibility API). _timed wraps each REST call so
    # the UI's API execution theater still gets per-call latency.
    trace: list = []
    num = _timed(
        "SDK", "phone_numbers.get",
        lambda: client.phone_numbers.get(sid),
        trace,
    )
    e164 = num.get("number")
    assignment = _timed(
        "Fabric", "assign_phone_route",
        lambda: assign_number_to_agent(e164, public_base=public_base, route=route, client=client),
        trace,
    )
    setup = {
        "sid": num.get("id"),
        "phone_number": e164,
        "friendly_name": num.get("name") or "",
        "route": route,
        "source": "existing",
        **assignment,
        "_trace": trace,
    }
    save_setup({k: v for k, v in setup.items() if k != "_trace"})
    return setup


def purchase_and_configure(phone_number: str, route: str, public_base: str) -> dict:
    """Buy `phone_number` (Relay REST), then assign it to the agent's SWML webhook."""
    client = _client()
    trace: list = []
    bought = _timed(
        "SDK", "phone_numbers.create",
        lambda: client.phone_numbers.create(number=phone_number),
        trace,
    )
    e164 = bought.get("number", phone_number)
    assignment = _timed(
        "Fabric", "assign_phone_route",
        lambda: assign_number_to_agent(e164, public_base=public_base, route=route, client=client),
        trace,
    )
    setup = {
        "sid": bought.get("id"),
        "phone_number": e164,
        # The Relay purchase API takes no name; FRIENDLY_NAME is for local display.
        "friendly_name": bought.get("name") or FRIENDLY_NAME,
        "route": route,
        "source": "purchased",
        **assignment,
        "_trace": trace,
    }
    save_setup({k: v for k, v in setup.items() if k != "_trace"})
    return setup


def repoint_to_route(route: str, public_base: str) -> dict:
    """Repoint the saved number to a different step.

    Re-runs the assignment: this updates the SWML webhook's primary_request_url to
    the new step AND (idempotently) ensures the number is routed to the resource,
    so it also heals a number that was saved but never assigned.
    """
    setup = load_setup()
    phone_number = setup.get("phone_number")
    if not phone_number:
        raise RuntimeError("no provisioned number; run setup first")
    trace: list = []
    assignment = _timed(
        "Fabric", "assign_phone_route",
        lambda: assign_number_to_agent(phone_number, public_base=public_base, route=route),
        trace,
    )
    setup.update({"route": route, **assignment})
    save_setup(setup)
    setup["_trace"] = trace
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
