"""
Step 12: REST pillar - subscriber token + agent provisioning
============================================================
Runs as a standalone script (the landing page kicks it off via POST /run/rest
and streams stdout over SSE). main.py also imports ensure_agent_handler() and
mint_subscriber_token() so the live click-to-call step (13) uses exactly what
this lesson teaches.

Capabilities:
  1. List phone numbers on the project (classic LaML REST client warm-up)
  2. Provision the AI agent as a dialable Fabric resource (external SWML handler)
  3. Mint a short-lived subscriber token for the browser SDK

Cross-process address cache:
  The REST demo subprocess and the live /api/relay/config in the parent server
  both call ensure_agent_handler(). To avoid repeating the slow Fabric listing
  call, the resolved audio address is written to a small JSON file keyed by
  space, so whichever runs first warms the cache for the other.
"""

import json
import os
import pathlib
import sys
import time

import requests
from requests.auth import HTTPBasicAuth
from signalwire.rest import Client as RestClient

HANDLER_NAME = "Chicago Roadshow 2026 Agent"
DEFAULT_AGENT_PATH = "/step04"
AGENT_PATH = DEFAULT_AGENT_PATH  # back-compat alias for callers that import this
DEFAULT_REFERENCE = "roadshow-attendee"
FABRIC_TIMEOUT = 30  # seconds; the listing call on busy projects can be slow

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


def _fabric(method, path, **kwargs):
    # WHY raw requests: the Fabric REST API (subscriber tokens, resources) is
    # not exposed by the signalwire LaML client, so we call it directly.
    project, token, space = _creds()
    url = f"https://{space}{path}"
    _log(f"{method} {path}")
    t0 = time.monotonic()
    try:
        resp = requests.request(
            method,
            url,
            auth=HTTPBasicAuth(project, token),
            headers={"Accept": "application/json"},
            timeout=FABRIC_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as e:
        elapsed = time.monotonic() - t0
        _log(f"{method} {path} -> NETWORK ERROR after {elapsed:.1f}s: {e.__class__.__name__}: {e}")
        raise
    elapsed = time.monotonic() - t0
    _log(f"{method} {path} -> HTTP {resp.status_code} in {elapsed:.2f}s")
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


def ensure_agent_handler(public_base=None, route=None):
    """Find or create the agent's external SWML handler; return its audio address.

    If `route` is provided and differs from the existing handler's
    primary_request_url, the handler is updated in place so PSTN and browser
    dialing land on the same agent step.
    """
    global _agent_address_cache
    target_route = route or DEFAULT_AGENT_PATH
    target_url = f"{_public_base(public_base)}{target_route}"

    if _agent_address_cache and route is None:
        _log("address from process cache")
        return _agent_address_cache

    space = os.environ.get("SIGNALWIRE_SPACE", "")
    cached = _load_cache(space)
    if cached and route is None:
        _log(f"address from file cache: {cached}")
        _agent_address_cache = cached
        return cached

    _log("listing external SWML handlers")
    listing = _fabric("GET", "/api/fabric/resources/external_swml_handlers")
    handlers = listing.get("data", [])
    _log(f"found {len(handlers)} handler(s); matching name/display_name '{HANDLER_NAME}'")
    # WHY match both: the Fabric API uses 'name' when creating but some
    # endpoints surface the value as 'display_name' on the way back out.
    existing = next(
        (
            h for h in handlers
            if h.get("name") == HANDLER_NAME or h.get("display_name") == HANDLER_NAME
        ),
        None,
    )
    if existing:
        handler_id = existing["id"]
        _log(f"matched existing handler id={handler_id}")
        # If the caller asked for a specific route, keep the handler in sync.
        current_url = (existing.get("external_swml_handler") or {}).get("primary_request_url") or existing.get("primary_request_url")
        if route is not None and current_url != target_url:
            _log(f"updating handler primary_request_url -> {target_url}")
            _fabric(
                "PUT",
                f"/api/fabric/resources/external_swml_handlers/{handler_id}",
                json={
                    "name": HANDLER_NAME,
                    "used_for": "calling",
                    "primary_request_url": target_url,
                    "primary_request_method": "POST",
                },
            )
    else:
        _log("no match; creating handler")
        created = _fabric(
            "POST",
            "/api/fabric/resources/external_swml_handlers",
            json={
                "name": HANDLER_NAME,
                "used_for": "calling",
                "primary_request_url": target_url,
                "primary_request_method": "POST",
            },
        )
        handler_id = created["id"]
        _log(f"created handler id={handler_id} -> {target_url}")

    _log(f"fetching addresses for handler {handler_id}")
    addrs = _fabric(
        "GET",
        f"/api/fabric/resources/external_swml_handlers/{handler_id}/addresses",
    )
    address = addrs["data"][0]["channels"]["audio"]
    _log(f"agent dial address: {address}")
    _agent_address_cache = address
    _save_cache(space, address)
    return address


def mint_subscriber_token(reference=DEFAULT_REFERENCE):
    """Mint a short-lived subscriber token. Returns (token, subscriber_id)."""
    _log(f"minting subscriber token (reference={reference!r})")
    data = _fabric(
        "POST",
        "/api/fabric/subscribers/tokens",
        json={"reference": reference},
    )
    sid = data.get("subscriber_id", "")
    _log(f"minted token for subscriber_id={sid}")
    return data["token"], sid


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
