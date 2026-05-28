"""
Step 12: REST pillar - subscriber token + agent provisioning
============================================================
Runs as a standalone script (landing page kicks it off via POST /run/rest
and streams stdout over SSE). main.py also imports ensure_agent_handler()
and mint_subscriber_token() so the live click-to-call step (13) uses exactly
what this lesson teaches.

Capabilities:
  1. List phone numbers on the project (classic LaML REST client warm-up)
  2. Provision the AI agent as a dialable Fabric resource (external SWML handler)
  3. Mint a short-lived subscriber token for the browser SDK
"""

import os
import sys

import requests
from requests.auth import HTTPBasicAuth
from signalwire.rest import Client as RestClient

HANDLER_NAME = "Chicago Roadshow 2026 Agent"
AGENT_PATH = "/step11"
DEFAULT_REFERENCE = "roadshow-attendee"

# WHY cache: repeat runs and the live endpoint must not create duplicate handlers.
_agent_address_cache = None


def _creds():
    try:
        return (
            os.environ["SIGNALWIRE_PROJECT_ID"],
            os.environ["SIGNALWIRE_TOKEN"],
            os.environ["SIGNALWIRE_SPACE"],
        )
    except KeyError as missing:
        raise RuntimeError(f"missing required env var: {missing.args[0]}") from None


def _fabric(method, path, **kwargs):
    # WHY raw requests: the Fabric REST API (subscriber tokens, resources) is
    # not exposed by the signalwire LaML client, so we call it directly.
    project, token, space = _creds()
    resp = requests.request(
        method,
        f"https://{space}{path}",
        auth=HTTPBasicAuth(project, token),
        headers={"Accept": "application/json"},
        timeout=15,
        **kwargs,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _public_base(public_base=None):
    base = (
        public_base
        or os.environ.get("PUBLIC_BASE")
        or os.environ.get("SWML_PROXY_URL_BASE")
    )
    if not base:
        raise RuntimeError("no public base URL; set SWML_PROXY_URL_BASE or PUBLIC_BASE")
    return base.rstrip("/")


def ensure_agent_handler(public_base=None):
    """Find or create the agent's external SWML handler; return its audio address."""
    global _agent_address_cache
    if _agent_address_cache:
        return _agent_address_cache

    listing = _fabric("GET", "/api/fabric/resources/external_swml_handlers")
    existing = next(
        (h for h in listing.get("data", []) if h.get("name") == HANDLER_NAME),
        None,
    )
    if existing:
        handler_id = existing["id"]
    else:
        created = _fabric(
            "POST",
            "/api/fabric/resources/external_swml_handlers",
            json={
                "name": HANDLER_NAME,
                "used_for": "calling",
                "primary_request_url": f"{_public_base(public_base)}{AGENT_PATH}",
                "primary_request_method": "POST",
            },
        )
        handler_id = created["id"]

    addrs = _fabric(
        "GET",
        f"/api/fabric/resources/external_swml_handlers/{handler_id}/addresses",
    )
    address = addrs["data"][0]["channels"]["audio"]
    _agent_address_cache = address
    return address


def mint_subscriber_token(reference=DEFAULT_REFERENCE):
    """Mint a short-lived subscriber token. Returns (token, subscriber_id)."""
    data = _fabric(
        "POST",
        "/api/fabric/subscribers/tokens",
        json={"reference": reference},
    )
    return data["token"], data.get("subscriber_id", "")


def main():
    try:
        project, token, space = _creds()
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    print("--- Phone numbers on this project ---")
    # WHY the classic client here: shows the LaML REST client next to the
    # newer Fabric API used below. A creds failure here is non-fatal.
    try:
        client = RestClient(project, token, signalwire_space_url=space)
        for num in client.incoming_phone_numbers.list(limit=20):
            print(num.phone_number, "|", num.friendly_name)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not list numbers: {e}", file=sys.stderr)

    print("\n--- Provisioning the agent as a Fabric resource ---")
    try:
        address = ensure_agent_handler()
        print("agent dial address:", address)
    except Exception as e:  # noqa: BLE001
        print(f"[error] could not provision agent handler: {e}", file=sys.stderr)
        return 1

    print("\n--- Minting a subscriber token ---")
    try:
        reference = os.environ.get("SUBSCRIBER_REFERENCE", DEFAULT_REFERENCE)
        tok, sub_id = mint_subscriber_token(reference)
        print("subscriber_id:", sub_id)
        masked = (tok[:12] + "..." + tok[-6:]) if len(tok) > 20 else "set"
        print("token (masked):", masked)
    except Exception as e:  # noqa: BLE001
        print(f"[error] could not mint subscriber token: {e}", file=sys.stderr)
        return 1

    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
