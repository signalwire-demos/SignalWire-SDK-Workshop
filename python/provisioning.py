"""
Workshop provisioning — does the SignalWire dashboard setup for the attendee,
end-to-end, via the SignalWire REST API (the agents-SDK Fabric/Relay client).

Everything goes through signalwire_agents.rest.client.SignalWireClient:
  - phone number search / buy / list / get   (Relay REST: client.phone_numbers)
  - SWML webhook resource + phone-route assignment (Fabric REST: client.fabric)

Workshop state (selected phone number + handler id) is not persisted here; the
caller owns a `setup` dict in its session and passes it in / receives it back.
Credentials are likewise passed in explicitly (per-session) rather than read
from the global process environment.
"""

from __future__ import annotations

import time

from python.steps import step12_rest_demo as step12

FRIENDLY_NAME = "Chicago Roadshow 2026 — Buddy"

HANDLER_NAME = step12.HANDLER_NAME
DEFAULT_AGENT_PATH = step12.DEFAULT_AGENT_PATH


def list_existing_numbers(creds, limit: int = 3) -> list[dict]:
    client = step12._client(creds)
    listing = client.phone_numbers.list(page_size=limit)
    return [{"sid": n.get("id"), "phone_number": n.get("number"), "friendly_name": n.get("name") or ""} for n in listing.get("data", [])]


def search_available(creds, area_code=None, limit: int = 3) -> list[dict]:
    client = step12._client(creds)
    params = {"number_type": "local", "max_results": limit}
    if area_code:
        params["areacode"] = area_code
    found = client.phone_numbers.search(**params)
    # Available-number search returns the number under "e164" (owned-number list
    # uses "number"); fall back so both shapes work. Search results carry no
    # "city" field — only "region" — so locality stays blank.
    return [{"phone_number": n.get("e164") or n.get("number"), "friendly_name": "", "locality": n.get("city") or "", "region": n.get("region") or ""} for n in found.get("data", [])]


def _timed(api: str, op: str, fn, trace: list):
    """Run fn(), append {api, op, ms} to trace. Returns fn's return value."""
    t0 = time.monotonic()
    try:
        return fn()
    finally:
        trace.append({"api": api, "op": op, "ms": int((time.monotonic() - t0) * 1000)})


def configure_existing(creds, sid: str, route: str, public_base: str, session_sid: str | None = None) -> dict:
    client = step12._client(creds)
    trace = []
    num = _timed("SDK", "phone_numbers.get", lambda: client.phone_numbers.get(sid), trace)
    e164 = num.get("number")
    assignment = _timed("Fabric", "assign_phone_route",
        lambda: step12.assign_number_to_agent(e164, public_base=public_base, route=route, client=client, sid=session_sid), trace)
    return {"sid": num.get("id"), "phone_number": e164, "friendly_name": num.get("name") or "",
            "route": route, "source": "existing", **assignment, "_trace": trace}


def purchase_and_configure(creds, phone_number: str, route: str, public_base: str, session_sid: str | None = None) -> dict:
    client = step12._client(creds)
    trace = []
    bought = _timed("SDK", "phone_numbers.create", lambda: client.phone_numbers.create(number=phone_number), trace)
    e164 = bought.get("number", phone_number)
    assignment = _timed("Fabric", "assign_phone_route",
        lambda: step12.assign_number_to_agent(e164, public_base=public_base, route=route, client=client, sid=session_sid), trace)
    return {"sid": bought.get("id"), "phone_number": e164, "friendly_name": bought.get("name") or FRIENDLY_NAME,
            "route": route, "source": "purchased", **assignment, "_trace": trace}


def repoint_to_route(creds, setup: dict, route: str, public_base: str) -> dict:
    phone_number = (setup or {}).get("phone_number")
    if not phone_number:
        raise RuntimeError("no provisioned number; run setup first")
    trace = []
    assignment = _timed("Fabric", "assign_phone_route",
        lambda: step12.assign_number_to_agent(phone_number, public_base=public_base, route=route, creds=creds), trace)
    updated = {**setup, "route": route, **assignment}
    updated["_trace"] = trace
    return updated


def setup_status(creds, setup: dict, public_base: str) -> dict:
    creds_ok = bool(creds and all(creds.get(k) for k in ("SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE")))
    return {"creds_configured": creds_ok, "public_base": public_base or "", "setup": setup or {},
            "default_route": step12.DEFAULT_AGENT_PATH, "handler_name": step12.HANDLER_NAME, "friendly_name": FRIENDLY_NAME}
