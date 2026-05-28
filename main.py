#!/usr/bin/env python3
"""
SignalWire AI Agent Workshop - Replit Edition
=============================================
Serves all workshop step agents simultaneously on separate routes,
plus a landing page at / with workshop info, SWML URLs, and setup instructions.

Add your optional Secrets, click Run, and open the web preview.

DEPLOYMENT NOTES (Replit Autoscale)
------------------------------------
1. The deploy URL is hardcoded in replit_setup.py (DEPLOY_URL).
   Update it there if the Replit app name changes.

2. After ANY code change, manually redeploy:
   Deployments tab -> Redeploy. Autoscale does NOT auto-redeploy on git push.

3. Verify deployment: GET https://<deployed-url>/validate
   All agents should show swaig_url_valid: true.

4. Run full test suite: python test_routes.py https://<deployed-url>
"""

import asyncio
import json
import os
import signal
import sys
import uuid
from replit_setup import startup
from urllib.parse import urlparse

# Detect public URL and report secret status (no longer blocks on missing creds)
base_url, auth_user, auth_pass = startup()

# ---------------------------------------------------------------------------
# SDK imports
# ---------------------------------------------------------------------------
from signalwire_agents import AgentServer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse, StreamingResponse

from python.steps.step04_hello import HelloAgent
from python.steps.step06_hardcoded_jokes import JokeAgent as HardcodedJokeAgent
from python.steps.step07_api_jokes import JokeAgent as ApiJokeAgent
from python.steps.step08_weather import WeatherJokeAgent
from python.steps.step09_polish import PolishedAgent
from python.steps.step10_skills import SkillsAgent
from python.steps.step11_complete import CompleteAgent

# ---------------------------------------------------------------------------
# Register all step agents on their own routes
# ---------------------------------------------------------------------------

STEPS = [
    ("/step04", HelloAgent,          "Step 4  - Hello Agent"),
    ("/step06", HardcodedJokeAgent,  "Step 6  - Hardcoded Jokes"),
    ("/step07", ApiJokeAgent,        "Step 7  - Live API Jokes"),
    ("/step08", WeatherJokeAgent,    "Step 8  - Weather + Jokes (DataMap)"),
    ("/step09", PolishedAgent,       "Step 9  - Polished Agent"),
    ("/step10", SkillsAgent,         "Step 10 - Agent with Skills"),
    ("/step11", CompleteAgent,       "Step 11 - Complete Agent"),
]

server = AgentServer(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# Each agent must know its route so the SDK generates correct webhook URLs
# (e.g., /step06/swaig/ not /swaig/).  We pass route= through the constructor
# so it's set during super().__init__() - the SDK's intended pattern.
registered_agents = {}
for route, agent_class, _desc in STEPS:
    agent = agent_class(route=route)
    server.register(agent, route)
    registered_agents[route] = agent

# ---------------------------------------------------------------------------
# Config endpoint - landing page fetches auth credentials dynamically
# ---------------------------------------------------------------------------

@server.app.get("/config")
async def get_config():
    """Return non-sensitive config for the landing page JS."""
    return JSONResponse({
        "auth_user": auth_user,
        "auth_pass": auth_pass,
        "base_url": base_url,
    })

# ---------------------------------------------------------------------------
# Validate endpoint - verify all webhook URLs have correct route prefixes
# ---------------------------------------------------------------------------

@server.app.get("/validate")
async def validate_urls():
    """Check every agent's webhook URLs include the correct route prefix."""
    results = []
    all_valid = True
    for route, _cls, desc in STEPS:
        agent = registered_agents.get(route)
        if not agent:
            results.append({"route": route, "error": "agent not registered"})
            all_valid = False
            continue

        swaig_url = agent._build_webhook_url("swaig")
        post_url = agent._build_webhook_url("post_prompt")

        # Mask credentials for display
        def mask(url):
            from urllib.parse import urlparse, urlunparse
            p = urlparse(url)
            if p.username:
                netloc = f"{p.username}:****@{p.hostname}"
                if p.port:
                    netloc += f":{p.port}"
                return urlunparse(p._replace(netloc=netloc))
            return url

        swaig_ok = route in swaig_url
        post_ok = route in post_url
        if not swaig_ok or not post_ok:
            all_valid = False

        func_names = []
        if hasattr(agent, '_tool_registry') and hasattr(agent._tool_registry, '_swaig_functions'):
            func_names = list(agent._tool_registry._swaig_functions.keys())

        results.append({
            "route": route,
            "name": agent.get_name(),
            "description": desc,
            "swaig_url": mask(swaig_url),
            "post_prompt_url": mask(post_url),
            "swaig_url_valid": swaig_ok,
            "post_prompt_url_valid": post_ok,
            "functions": func_names,
        })

    return JSONResponse({
        "status": "ok" if all_valid else "error",
        "base_url": base_url,
        "agent_count": len(results),
        "agents": results,
    })

# ---------------------------------------------------------------------------
# SWAIG/post_prompt fallback - catches calls when URL generation omits the
# step prefix (e.g., /swaig/ instead of /step06/swaig/).  Dispatches to the
# correct agent by matching the function name in the request body.
# ---------------------------------------------------------------------------

from fastapi import Request, Response, HTTPException
import json as _json

@server.app.post("/swaig")
@server.app.post("/swaig/")
async def root_swaig_fallback(request: Request):
    """Dispatch SWAIG calls that land on root /swaig/ to the correct agent."""
    body = await request.body()
    try:
        data = _json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    func_name = data.get("function", "")

    # Find the agent that owns this function
    for _route, agent in registered_agents.items():
        if hasattr(agent, '_tool_registry') and hasattr(agent._tool_registry, '_swaig_functions'):
            if func_name in agent._tool_registry._swaig_functions:
                result = agent._execute_swaig_function(func_name, data, None, None)
                return JSONResponse(result if isinstance(result, dict) else {"response": str(result)})

    raise HTTPException(status_code=404, detail="Function not found")

@server.app.post("/post_prompt")
@server.app.post("/post_prompt/")
async def root_post_prompt_fallback(request: Request):
    """Dispatch post_prompt calls that land on root /post_prompt/."""
    body = await request.body()
    try:
        data = _json.loads(body)
    except Exception:
        data = {}

    # Try each agent's on_summary handler
    for _route, agent in registered_agents.items():
        if hasattr(agent, 'on_summary'):
            try:
                summary = data.get("post_prompt_data", {}).get("raw", "")
                agent.on_summary(summary, data)
                return JSONResponse({"status": "ok"})
            except Exception:
                continue

    return JSONResponse({"status": "ok"})

# ---------------------------------------------------------------------------
# Source viewer - lets the landing page link to /source/agents/step04_hello.py
# ---------------------------------------------------------------------------

ALLOWED_SOURCE_DIR = os.path.join(os.path.dirname(__file__), "agents")

@server.app.get("/source/{file_path:path}")
async def view_source(file_path: str):
    """Serve agent source files as plain text for easy reading."""
    full = os.path.normpath(os.path.join(os.path.dirname(__file__), file_path))
    # Only serve files inside the agents/ directory
    if not full.startswith(os.path.normpath(ALLOWED_SOURCE_DIR)):
        return PlainTextResponse("Forbidden", status_code=403)
    if not os.path.isfile(full):
        return PlainTextResponse("Not found", status_code=404)
    with open(full) as f:
        return PlainTextResponse(f.read())

# ---------------------------------------------------------------------------
# Landing page - serve static files from web/
# ---------------------------------------------------------------------------
# WHY conditional: web/ does not exist until Task 8 lands; this keeps main.py
# runnable in interim states without 500ing on missing assets.
import os.path
if os.path.isdir("web"):
    server.app.mount("/static", StaticFiles(directory="web"), name="static")

    @server.app.get("/")
    async def landing():
        return FileResponse("web/index.html")

# ---------------------------------------------------------------------------
# REST + RELAY pillar Run endpoints (steps 12 + 13)
# ---------------------------------------------------------------------------

# In-flight subprocesses keyed by pillar so a new POST cancels the old one.
_INFLIGHT: dict[str, dict] = {}

PILLAR_TO_SCRIPT = {
    "rest": "python/steps/step12_rest_demo.py",
}

# WHY only project/token/space: step 12 now provisions the agent and mints a
# subscriber token; it no longer sends SMS, so SMS_FROM/SMS_TO are gone.
PILLAR_REQUIRED_ENV = {
    "rest": ["SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE"],
}


async def _terminate_inflight(state: dict) -> None:
    # WHY two-stage: give the script a chance to clean up websockets and
    # in-flight API calls before we hard-kill it.
    proc = state.get("proc")
    if proc and proc.returncode is None:
        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    queue: asyncio.Queue = state["queue"]
    await queue.put({"event": "cancelled", "data": "previous run cancelled"})
    await queue.put(None)


async def _pump(stream, queue: asyncio.Queue, stream_name: str) -> None:
    while True:
        line = await stream.readline()
        if not line:
            return
        await queue.put({
            "event": stream_name,
            "data": line.decode("utf-8", errors="replace").rstrip(),
        })


@server.app.get("/run/{pillar}/inputs")
async def run_inputs(pillar: str):
    if pillar not in PILLAR_REQUIRED_ENV:
        return JSONResponse({"error": "unknown pillar"}, status_code=404)
    required = PILLAR_REQUIRED_ENV[pillar]
    missing = [k for k in required if not os.environ.get(k)]
    return {"pillar": pillar, "required": required, "missing": missing}


@server.app.post("/run/{pillar}")
async def run_pillar(pillar: str, request: Request):
    if pillar not in PILLAR_TO_SCRIPT:
        return JSONResponse({"error": "unknown pillar"}, status_code=404)
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    inputs = body.get("inputs", {}) if isinstance(body, dict) else {}

    if pillar in _INFLIGHT:
        await _terminate_inflight(_INFLIGHT.pop(pillar))

    run_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    env = {**os.environ, **{str(k): str(v) for k, v in inputs.items()}}

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", PILLAR_TO_SCRIPT[pillar],
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def supervise():
        await asyncio.gather(
            _pump(proc.stdout, queue, "stdout"),
            _pump(proc.stderr, queue, "stderr"),
        )
        rc = await proc.wait()
        await queue.put({"event": "exit", "data": str(rc)})
        await queue.put(None)
        # Only drop if this is still the current run; a newer POST may have
        # already taken our slot.
        if _INFLIGHT.get(pillar, {}).get("run_id") == run_id:
            _INFLIGHT.pop(pillar, None)

    asyncio.create_task(supervise())
    _INFLIGHT[pillar] = {"proc": proc, "queue": queue, "run_id": run_id}
    return {"pillar": pillar, "run_id": run_id}


@server.app.get("/run/{pillar}/stream/{run_id}")
async def run_stream(pillar: str, run_id: str):
    state = _INFLIGHT.get(pillar)
    if not state or state["run_id"] != run_id:
        return JSONResponse({"error": "no such run"}, status_code=404)
    queue: asyncio.Queue = state["queue"]

    async def gen():
        while True:
            item = await queue.get()
            if item is None:
                yield "event: end\ndata: done\n\n"
                return
            payload = json.dumps({"event": item["event"], "data": item["data"]})
            yield f"event: {item['event']}\ndata: {payload}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

# ---------------------------------------------------------------------------
# Step 13 RELAY: subscriber token + agent address for the browser SDK
# ---------------------------------------------------------------------------

@server.app.get("/api/relay/config")
async def relay_config():
    """Mint a fresh subscriber token and return the agent dial address.

    Reuses the step 12 helpers so the browser gets exactly what the REST
    lesson teaches. Admin creds never leave the server; only the short-lived
    subscriber token reaches the page.
    """
    from python.steps.step12_rest_demo import (
        DEFAULT_REFERENCE,
        ensure_agent_handler,
        mint_subscriber_token,
    )

    print("[relay/config] request received", flush=True)
    try:
        reference = os.environ.get("SUBSCRIBER_REFERENCE", DEFAULT_REFERENCE)
        print(f"[relay/config] reference={reference!r}", flush=True)
        print("[relay/config] -> ensure_agent_handler", flush=True)
        # WHY to_thread: the helpers use blocking requests; keep the loop free.
        destination = await asyncio.to_thread(ensure_agent_handler, base_url)
        print(f"[relay/config]    destination={destination}", flush=True)
        print("[relay/config] -> mint_subscriber_token", flush=True)
        token, sub_id = await asyncio.to_thread(mint_subscriber_token, reference)
        print(f"[relay/config]    minted token ({len(token)} chars) for {sub_id}", flush=True)
        return JSONResponse({"token": token, "destination": destination})
    except Exception as e:  # noqa: BLE001 - report a clean error, never a 500 stack
        print(f"[relay/config] FAILED: {e.__class__.__name__}: {e}", flush=True)
        return JSONResponse({"error": str(e)}, status_code=503)

# ---------------------------------------------------------------------------
# Shared credentials: one panel above both pillars posts here. Writing into
# os.environ means BOTH the REST subprocess (it inherits os.environ when spawned
# by /run/rest) and the RELAY endpoint (it reads os.environ) pick up the same
# creds. WHY a server-side store: a workshop fork is single-tenant, so holding
# creds in the process for the session is the simplest way to share them across
# pillars without ever putting the admin token in the browser.
# ---------------------------------------------------------------------------

_CRED_KEYS = ("SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE")


def _credentials_status():
    return {
        "configured": all(os.environ.get(k) for k in _CRED_KEYS),
        "fields": {
            "SIGNALWIRE_PROJECT_ID": bool(os.environ.get("SIGNALWIRE_PROJECT_ID")),
            "SIGNALWIRE_TOKEN": bool(os.environ.get("SIGNALWIRE_TOKEN")),
            # WHY value not bool: the space is a non-secret domain, so echo it to
            # prefill the form on reload. Project id and token stay masked.
            "SIGNALWIRE_SPACE": os.environ.get("SIGNALWIRE_SPACE", ""),
        },
    }


@server.app.get("/api/credentials/status")
async def credentials_status():
    return JSONResponse(_credentials_status())


@server.app.post("/api/credentials")
async def set_credentials(request: Request):
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected a JSON object"}, status_code=400)
    for k in _CRED_KEYS:
        if k in body:
            value = str(body[k]).strip()
            if value:
                os.environ[k] = value
            else:
                os.environ.pop(k, None)  # empty value clears it
    return JSONResponse(_credentials_status())

# ---------------------------------------------------------------------------
# Workshop setup — automate phone-number + webhook plumbing via REST.
# Endpoints used by the new onboarding wizard and the per-agent
# "Point my phone number here" buttons.
# ---------------------------------------------------------------------------

VALID_AGENT_ROUTES = {r for r, _, _ in STEPS}


def _require_creds():
    missing = [k for k in _CRED_KEYS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"missing credentials: {', '.join(missing)}")


def _require_public_base():
    if not base_url:
        raise RuntimeError("no public URL detected; set SWML_PROXY_URL_BASE or REPLIT_DEV_DOMAIN")
    return base_url


def _normalize_route(route: str) -> str:
    if not route or not route.startswith("/"):
        raise RuntimeError("route must start with /")
    if route not in VALID_AGENT_ROUTES:
        raise RuntimeError(f"unknown agent route: {route}")
    return route


@server.app.get("/api/setup/status")
async def setup_status():
    from python.provisioning import setup_status as _status
    return JSONResponse(_status(base_url or ""))


@server.app.get("/api/setup/numbers")
async def setup_numbers():
    """Existing IncomingPhoneNumbers on the project (max 3)."""
    try:
        _require_creds()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    from python.provisioning import list_existing_numbers
    try:
        nums = await asyncio.to_thread(list_existing_numbers, 3)
        return JSONResponse({"numbers": nums})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/search")
async def setup_search(request: Request):
    """Search up to 3 available US local numbers, with optional area_code filter."""
    try:
        _require_creds()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    area_code = body.get("area_code")
    if area_code and not str(area_code).isdigit():
        return JSONResponse({"error": "area_code must be digits"}, status_code=400)
    from python.provisioning import search_available
    try:
        nums = await asyncio.to_thread(search_available, str(area_code) if area_code else None, 3)
        return JSONResponse({"numbers": nums, "area_code": area_code or None})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/select")
async def setup_select(request: Request):
    """Configure a chosen number — either existing (by sid) or to-be-purchased (by phone_number)."""
    try:
        _require_creds()
        public = _require_public_base()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    route = body.get("route", "/step04")
    try:
        route = _normalize_route(route)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    sid = body.get("sid")
    phone_to_buy = body.get("phone_number")
    if not sid and not phone_to_buy:
        return JSONResponse({"error": "either sid or phone_number is required"}, status_code=400)
    from python.provisioning import configure_existing, purchase_and_configure
    try:
        if sid:
            result = await asyncio.to_thread(configure_existing, sid, route, public)
        else:
            result = await asyncio.to_thread(purchase_and_configure, phone_to_buy, route, public)
        return JSONResponse({"setup": result})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/route")
async def setup_route(request: Request):
    """Re-point the saved number at a different agent step (SWML webhook)."""
    try:
        _require_creds()
        public = _require_public_base()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    route = body.get("route")
    try:
        route = _normalize_route(route)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    from python.provisioning import repoint_to_route
    try:
        result = await asyncio.to_thread(repoint_to_route, route, public)
        return JSONResponse({"setup": result})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/reset")
async def setup_reset():
    """Forget the persisted phone number/handler. Does NOT release the number."""
    from python.provisioning import clear_setup
    clear_setup()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Print SWML URLs to console
# ---------------------------------------------------------------------------

if base_url:
    p = urlparse(base_url)
    print("\n" + "=" * 60)
    print("  SWML URLs - paste any into your SignalWire dashboard")
    print("=" * 60 + "\n")
    for route, _cls, desc in STEPS:
        url = f"{p.scheme}://{auth_user}:{auth_pass}@{p.netloc}{route}"
        print(f"  {desc}")
        print(f"  {url}\n")
    print("=" * 60)
    print(f"\n  Landing page: {base_url}\n")
else:
    print("\nNo public URL - SWML URLs will be available once")
    print("REPLIT_DEV_DOMAIN or SWML_PROXY_URL_BASE is set.\n")

# ---------------------------------------------------------------------------
# Startup validation - catch webhook URL problems before accepting traffic
# ---------------------------------------------------------------------------

if base_url:
    errors = []
    for route, agent in registered_agents.items():
        swaig_url = agent._build_webhook_url("swaig")
        post_url = agent._build_webhook_url("post_prompt")
        if route not in swaig_url:
            errors.append(f"  {route}: swaig URL missing prefix -> {swaig_url}")
        if route not in post_url:
            errors.append(f"  {route}: post_prompt URL missing prefix -> {post_url}")
    if errors:
        print("\n*** WEBHOOK URL VALIDATION FAILED ***")
        for e in errors:
            print(e)
        print("*** Fix: ensure agent.route is set before server.register() ***\n")
    else:
        print(f"\nWebhook URL validation passed for {len(registered_agents)} agents.")

port = int(os.environ.get("PORT", 5000))
print(f"\nStarting server with all agents on port {port}...\n")

server.run()
