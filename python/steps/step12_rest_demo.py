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
  3. Mint tokens for the browser SDK: the live /api/relay/config path mints a
     scoped guest token; the standalone main() script still mints a subscriber token

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
import time
import requests
from urllib.parse import urlsplit, urlunsplit, quote

from signalwire_agents.rest.client import SignalWireClient
from signalwire_agents.rest._base import SignalWireRestError

from creds_normalize import normalize_space

HANDLER_NAME = "Agents SDK Workshop Agent"
DEFAULT_AGENT_PATH = "/step04"
AGENT_PATH = DEFAULT_AGENT_PATH  # alias for callers that import this
DEFAULT_REFERENCE = "workshop-attendee"

# WHY in the project root: both the subprocess and the parent server have CWD
# at the project root when launched as documented, and the resolved path here
# is stable regardless of who imports the module.
_CACHE_FILE = pathlib.Path(__file__).resolve().parent.parent.parent / ".agent_handler_cache.json"

_agent_address_cache = None  # process-local fast path


def _log(msg):
    # Stdout, line-buffered: the SSE harness streams it; the parent server's
    # print() lands in its own log. WHY single prefix: easy to grep.
    print(f"[step12] {msg}", flush=True)


def _creds(creds=None):
    """Return (project, token, space). Prefer explicit creds (in-process,
    per-session); fall back to env (the standalone subprocess path).

    The space is re-normalized here as defense in depth: session creds arrive
    normalized, but env creds (Replit Secrets, .env) can hold any pasted form,
    e.g. 'https://demo.signalwire.com'.
    """
    if creds:
        try:
            triple = (creds["SIGNALWIRE_PROJECT_ID"], creds["SIGNALWIRE_TOKEN"], creds["SIGNALWIRE_SPACE"])
        except KeyError as missing:
            raise RuntimeError(f"missing required credential: {missing.args[0]}") from None
    else:
        try:
            triple = (
                os.environ["SIGNALWIRE_PROJECT_ID"],
                os.environ["SIGNALWIRE_TOKEN"],
                os.environ["SIGNALWIRE_SPACE"],
            )
        except KeyError as missing:
            raise RuntimeError(f"missing required env var: {missing.args[0]}") from None
    project, token, space = triple
    try:
        space = normalize_space(space)
    except ValueError as e:
        raise RuntimeError(f"invalid SIGNALWIRE_SPACE: {e}") from None
    return (project.strip(), token.strip(), space)


def _client(creds=None):
    """SignalWire REST client (Fabric + Relay namespaces) from the agents SDK.

    WHY pass token explicitly: the SDK defaults the token env var to
    SIGNALWIRE_API_TOKEN, but the workshop standardizes on SIGNALWIRE_TOKEN.
    """
    project, token, space = _creds(creds)
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


def _authed_url(base, route, sid=None):
    """Build the URL SignalWire fetches, with the agent's Basic auth embedded.

    The agent requires Basic auth on its routes, so the SWML webhook's
    primary_request_url must carry credentials (same as the console output and
    the agent's own swaig URLs). Without them SignalWire gets 401, not SWML.

    When `sid` is given it is appended as a `?sid=` query param so the agent's
    on_swml_request can stamp the originating workshop session into global_data.
    """
    user = quote(os.environ.get("SWML_BASIC_AUTH_USER", "workshop"), safe="")
    pw = quote(os.environ.get("SWML_BASIC_AUTH_PASSWORD", "password"), safe="")
    parts = urlsplit(base)
    netloc = f"{user}:{pw}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    query = f"sid={quote(sid, safe='')}" if sid else ""
    return urlunsplit((parts.scheme, netloc, route, query, ""))


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


def ensure_agent_handler(public_base=None, route=None, client=None, creds=None, cache=None, sid=None):
    """Find or create the agent's SWML webhook resource; return its audio address.

    If `route` is provided and differs from the resource's primary_request_url,
    the resource is updated in place so PSTN and browser dialing land on the same
    agent step.

    When `sid` is given it is embedded as a `?sid=` query param in the
    primary_request_url so the agent's on_swml_request can stamp the originating
    workshop session into global_data.
    """
    global _agent_address_cache
    target_route = route or DEFAULT_AGENT_PATH
    target_url = _authed_url(_public_base(public_base), target_route, sid=sid)

    if cache is not None:
        if cache.get("agent_address") and route is None:
            _log("address from session cache")
            return cache["agent_address"]
    else:
        if _agent_address_cache and route is None:
            _log("address from process cache")
            return _agent_address_cache
        space = os.environ.get("SIGNALWIRE_SPACE", "")
        cached = _load_cache(space)
        if cached and route is None:
            _log(f"address from file cache: {cached}")
            _agent_address_cache = cached
            return cached

    client = client or _client(creds)
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
    channels = addrs["data"][0]["channels"]
    # Prefer the video channel (Buddy renders a video avatar; the click-to-call
    # widget is video-capable); fall back to audio for audio-only resources.
    address = channels.get("video") or channels["audio"]
    _log(f"agent dial address: {address}")
    if cache is not None:
        cache["agent_address"] = address
    else:
        _agent_address_cache = address
        _save_cache(os.environ.get("SIGNALWIRE_SPACE", ""), address)
    return address


def assign_number_to_agent(e164, public_base=None, route=None, client=None, creds=None, sid=None):
    """Route a PSTN number to the agent's SWML webhook resource (Call Fabric).

    Assigns the number to the SWML webhook Resource as a phone route, exactly
    like the dashboard's "Assign Resource -> SWML Script (External URL)" flow.

    When `sid` is given it is threaded into ensure_agent_handler so the
    provisioned URL carries ?sid= for session stamping.

    Returns {"resource_id", "phone_route_id"}.
    """
    client = client or _client(creds)
    # Ensure the resource exists and points at the requested route, then find it.
    ensure_agent_handler(public_base=public_base, route=route, client=client, sid=sid)
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


def mint_subscriber_token(reference=DEFAULT_REFERENCE, client=None, creds=None):
    """Mint a short-lived subscriber token. Returns (token, subscriber_id)."""
    client = client or _client(creds)
    _log(f"minting subscriber token (reference={reference!r})")
    data = client.fabric.tokens.create_subscriber_token(reference=reference)
    sid = data.get("subscriber_id", "")
    _log(f"minted token for subscriber_id={sid}")
    return data["token"], sid


def agent_address_id(client=None, creds=None):
    """Return the Fabric address UUID for the agent's SWML webhook resource.

    Guest tokens are scoped by address id (not the dial string). The dial
    string still comes from ensure_agent_handler(); this returns the matching
    address's `id` from the same addresses listing.
    """
    client = client or _client(creds)
    # WHY re-resolve: the address cache stores only the dial string, not the
    # resource id, so this function must look it up independently to stay standalone.
    resource_id, _ = _find_swml_webhook(client)
    if not resource_id:
        raise RuntimeError("agent SWML webhook not found; provision the agent first")
    addrs = client.fabric.swml_webhooks.list_addresses(resource_id)
    data = addrs.get("data", [])
    if not data:
        raise RuntimeError("agent SWML webhook resource has no addresses; re-provision the agent")
    return data[0]["id"]


def mint_guest_token(address_id, creds=None, ttl_secs=3600 * 24):
    """Mint a scoped guest token for the browser SDK. No subscriber created.

    Matches the canonical demos (cinebot/example): POST to the Fabric guests
    endpoint with project Basic auth, scoped to a single address. Returns the
    token string.
    """
    project, token, space = _creds(creds)
    _log(f"minting guest token (address_id={address_id})")
    resp = requests.post(
        f"https://{space}/api/fabric/guests/tokens",
        json={"allowed_addresses": [address_id], "expire_at": int(time.time()) + ttl_secs},
        auth=(project, token),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=10,
    )
    if not resp.ok:
        # The body names the actual problem (bad address id, auth, plan limits);
        # without it a failed mint surfaces only as an opaque 4xx in the caller.
        _log(f"guest token mint FAILED: HTTP {resp.status_code} from "
             f"https://{space}/api/fabric/guests/tokens: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()["token"]


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
