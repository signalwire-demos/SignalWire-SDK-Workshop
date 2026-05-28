"""
Step 12: REST pillar - subscriber token + agent provisioning
============================================================
Runs as a standalone script (the landing page kicks it off via POST /run/rest
and streams stdout over SSE). main.py also imports ensure_agent_handler() and
mint_subscriber_token() so the live click-to-call step (13) uses exactly what
this lesson teaches.

Everything here uses the SignalWire REST API through the agents SDK's REST
client (signalwire_agents.rest.client.SignalWireClient): the Fabric namespace
for SWML webhook resources + subscriber tokens, and the Relay namespace for
phone numbers.

Capabilities:
  1. List phone numbers on the project (Relay REST: client.phone_numbers.list)
  2. Provision the AI agent as a dialable SWML webhook resource (Fabric REST)
  3. Mint a short-lived subscriber token for the browser SDK

Cross-process address cache:
  The REST demo subprocess and the live /api/relay/config in the parent server
  both call ensure_agent_handler(). To avoid repeating the slow resource listing
  call, the resolved audio address is written to a small JSON file keyed by
  space, so whichever runs first warms the cache for the other.
"""

import json
import os
import pathlib
import sys
from urllib.parse import urlsplit, urlunsplit, quote

from signalwire_agents.rest.client import SignalWireClient
from signalwire_agents.rest._base import SignalWireRestError

HANDLER_NAME = "Chicago Roadshow 2026 Agent"
DEFAULT_AGENT_PATH = "/step04"
AGENT_PATH = DEFAULT_AGENT_PATH  # alias for callers that import this
DEFAULT_REFERENCE = "roadshow-attendee"

# WHY in the project root: both the subprocess and the parent server have CWD
# at the project root when launched as documented, and the resolved path here
# is stable regardless of who imports the module.
_CACHE_FILE = pathlib.Path(__file__).resolve().parent.parent.parent / ".agent_handler_cache.json"

_agent_address_cache = None  # process-local fast path


def _log(msg):
    # Stdout, line-buffered: the SSE harness streams it; the parent server's
    # print() lands in its own log. WHY single prefix: easy to grep.
    print(f"[step12] {msg}", flush=True)


def _creds():
    try:
        return (
            os.environ["SIGNALWIRE_PROJECT_ID"],
            os.environ["SIGNALWIRE_TOKEN"],
            os.environ["SIGNALWIRE_SPACE"],
        )
    except KeyError as missing:
        raise RuntimeError(f"missing required env var: {missing.args[0]}") from None


def _client():
    """SignalWire REST client (Fabric + Relay namespaces) from the agents SDK.

    WHY pass token explicitly: the SDK defaults the token env var to
    SIGNALWIRE_API_TOKEN, but the workshop standardizes on SIGNALWIRE_TOKEN.
    """
    project, token, space = _creds()
    return SignalWireClient(project=project, token=token, host=space)


def _public_base(public_base=None):
    base = (
        public_base
        or os.environ.get("PUBLIC_BASE")
        or os.environ.get("SWML_PROXY_URL_BASE")
    )
    if not base:
        raise RuntimeError("no public base URL; set SWML_PROXY_URL_BASE or PUBLIC_BASE")
    return base.rstrip("/")


def _authed_url(base, route):
    """Build the URL SignalWire fetches, with the agent's Basic auth embedded.

    The agent requires Basic auth on its routes, so the SWML webhook's
    primary_request_url must carry credentials (same as the console output and
    the agent's own swaig URLs). Without them SignalWire gets 401, not SWML.
    """
    user = quote(os.environ.get("SWML_BASIC_AUTH_USER", "workshop"), safe="")
    pw = quote(os.environ.get("SWML_BASIC_AUTH_PASSWORD", "password"), safe="")
    parts = urlsplit(base)
    netloc = f"{user}:{pw}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, route, "", ""))


def _load_cache(space):
    try:
        data = json.loads(_CACHE_FILE.read_text())
        if data.get("space") == space and data.get("address"):
            return data["address"]
    except (OSError, ValueError):
        pass
    return None


def _save_cache(space, address):
    try:
        _CACHE_FILE.write_text(json.dumps({"space": space, "address": address}))
    except OSError as e:
        _log(f"cache write failed: {e}")


def _find_swml_webhook(client):
    """Return (resource_id, primary_request_url) for the agent's SWML webhook.

    Returns (None, None) when no resource named HANDLER_NAME exists yet.
    """
    _log("listing SWML webhook resources")
    listing = client.fabric.swml_webhooks.list()
    # WHY match both name and display_name: the API takes 'name' on create but
    # surfaces the value as 'display_name' on the way back out.
    for h in listing.get("data", []):
        if HANDLER_NAME in (h.get("name"), h.get("display_name")):
            cfg = h.get("swml_webhook") or {}
            return h["id"], cfg.get("primary_request_url") or h.get("primary_request_url")
    return None, None


def ensure_agent_handler(public_base=None, route=None, client=None):
    """Find or create the agent's SWML webhook resource; return its audio address.

    If `route` is provided and differs from the resource's primary_request_url,
    the resource is updated in place so PSTN and browser dialing land on the same
    agent step.
    """
    global _agent_address_cache
    target_route = route or DEFAULT_AGENT_PATH
    target_url = _authed_url(_public_base(public_base), target_route)

    if _agent_address_cache and route is None:
        _log("address from process cache")
        return _agent_address_cache

    space = os.environ.get("SIGNALWIRE_SPACE", "")
    cached = _load_cache(space)
    if cached and route is None:
        _log(f"address from file cache: {cached}")
        _agent_address_cache = cached
        return cached

    client = client or _client()
    resource_id, current_url = _find_swml_webhook(client)
    if resource_id:
        _log(f"matched existing SWML webhook id={resource_id}")
        # If the caller asked for a specific route, keep the resource in sync.
        if route is not None and current_url != target_url:
            _log(f"updating primary_request_url -> {target_url}")
            client.fabric.swml_webhooks.update(
                resource_id,
                name=HANDLER_NAME,
                used_for="calling",
                primary_request_url=target_url,
                primary_request_method="POST",
            )
    else:
        _log("no match; creating SWML webhook")
        created = client.fabric.swml_webhooks.create(
            name=HANDLER_NAME,
            used_for="calling",
            primary_request_url=target_url,
            primary_request_method="POST",
        )
        resource_id = created["id"]
        _log(f"created SWML webhook id={resource_id} -> {target_url}")

    _log(f"fetching addresses for SWML webhook {resource_id}")
    addrs = client.fabric.swml_webhooks.list_addresses(resource_id)
    address = addrs["data"][0]["channels"]["audio"]
    _log(f"agent dial address: {address}")
    _agent_address_cache = address
    _save_cache(space, address)
    return address


def assign_number_to_agent(e164, public_base=None, route=None, client=None):
    """Route a PSTN number to the agent's SWML webhook resource (Call Fabric).

    Assigns the number to the SWML webhook Resource as a phone route, exactly
    like the dashboard's "Assign Resource -> SWML Script (External URL)" flow.

    Returns {"resource_id", "phone_route_id"}.
    """
    client = client or _client()
    # Ensure the resource exists and points at the requested route, then find it.
    ensure_agent_handler(public_base=public_base, route=route, client=client)
    resource_id, _ = _find_swml_webhook(client)
    if not resource_id:
        raise RuntimeError("agent SWML webhook not found after ensure_agent_handler()")

    # Resolve the number's id (used as phone_route_id) from its E.164 value.
    _log(f"looking up phone number {e164}")
    found = client.phone_numbers.list(filter_number=e164)
    nums = found.get("data", [])
    if not nums:
        raise RuntimeError(f"phone number {e164} not found on this space")
    phone_route_id = nums[0]["id"]

    _log(f"assigning {e164} (route_id={phone_route_id}) -> resource {resource_id}")
    # Idempotent: re-running setup or repointing to another step re-issues this
    # call. If the number is already routed to the resource, treat it as success.
    try:
        client.fabric.resources.assign_phone_route(
            resource_id, phone_route_id=phone_route_id, handler="calling"
        )
    except SignalWireRestError as e:
        if e.status_code in (409, 422):
            _log(f"already assigned (HTTP {e.status_code}); leaving existing route in place")
        else:
            raise
    return {"resource_id": resource_id, "phone_route_id": phone_route_id}


def mint_subscriber_token(reference=DEFAULT_REFERENCE, client=None):
    """Mint a short-lived subscriber token. Returns (token, subscriber_id)."""
    client = client or _client()
    _log(f"minting subscriber token (reference={reference!r})")
    data = client.fabric.tokens.create_subscriber_token(reference=reference)
    sid = data.get("subscriber_id", "")
    _log(f"minted token for subscriber_id={sid}")
    return data["token"], sid


def main():
    try:
        client = _client()
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    print("--- Phone numbers on this project ---")
    # Relay REST via the SDK: client.phone_numbers.list(). Non-fatal on failure.
    try:
        listing = client.phone_numbers.list(page_size=20)
        for num in listing.get("data", []):
            print(num.get("number"), "|", num.get("name") or "(no name)")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not list numbers: {e}", file=sys.stderr)

    print("\n--- Provisioning the agent as an SWML webhook resource ---")
    try:
        address = ensure_agent_handler(client=client)
        print("agent dial address:", address)
    except Exception as e:  # noqa: BLE001
        print(f"[error] could not provision agent handler: {e}", file=sys.stderr)
        return 1

    print("\n--- Minting a subscriber token ---")
    try:
        reference = os.environ.get("SUBSCRIBER_REFERENCE", DEFAULT_REFERENCE)
        tok, sub_id = mint_subscriber_token(reference, client=client)
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
