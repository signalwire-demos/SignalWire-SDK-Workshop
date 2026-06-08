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
import session_store
import call_store
import config_store
from urllib.parse import urlparse


def _load_dotenv(path=".env"):
    """Local-dev convenience: load KEY=VALUE lines from a .env into os.environ.

    Only used for local testing. The file is gitignored and never deployed, so
    on Replit (which uses the Secrets tab) it simply does not exist and this is
    a no-op -- meaning workshop attendees are still prompted for their own
    credentials. Existing env vars are NEVER overwritten, so real environment
    variables / Replit Secrets always win over the file.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


# Load local .env (if present) BEFORE startup so credentials are available for
# the credentials-status endpoint and the panel auto-collapses during local dev.
_load_dotenv()

_SESSIONS = session_store.SessionStore(path=".workshop_sessions.json")
_SESSIONS.load()

# Runtime config (public URL + SWAIG basic auth), editable on the admin page
# instead of via Replit Secrets. Applied into the live process by _apply_config().
_CONFIG = config_store.ConfigStore(path=".workshop_config.json")
_CONFIG.load()


def _resolve_session_for_call(raw_data):
    """Map a post-prompt payload to its originating session.

    1. Prefer global_data.workshop_session_id (exact; stamped at SWML render).
    2. Match the SignalWire project_id (every post-prompt payload carries it;
       each attendee uses their own project). This is the reliable workhorse —
       confirmed against a real captured payload.
    3. Fall back to matching the provisioned phone number against to/from.
    Defensive: returns None on any mismatch and never raises.
    """
    try:
        raw_data = raw_data if isinstance(raw_data, dict) else {}

        gd = raw_data.get("global_data") or {}
        sid = gd.get("workshop_session_id") if isinstance(gd, dict) else None
        if sid:
            sess = _SESSIONS.get(sid)
            if sess:
                creds = sess.get("creds", {}) or {}
                return {"space": creds.get("SIGNALWIRE_SPACE"),
                        "project_id": creds.get("SIGNALWIRE_PROJECT_ID"),
                        "session_id": sid}

        project_id = raw_data.get("project_id")
        if project_id:
            for row in _SESSIONS.admin_snapshot():
                if row.get("project_id") == project_id:
                    return {"space": row["space"], "project_id": row["project_id"],
                            "session_id": row["session_id"]}

        swml = raw_data.get("SWMLVars") or raw_data.get("prompt_vars") or {}
        if not isinstance(swml, dict):
            swml = {}
        candidates = {swml.get("to"), swml.get("from"), raw_data.get("caller_id_num")}
        candidates.discard(None)
        for row in _SESSIONS.admin_snapshot():
            setup_num = row.get("agent_address") or ""
            sess = _SESSIONS.get(row["session_id"]) or {}
            provisioned = (sess.get("setup", {}) or {}).get("phone_number")
            if (provisioned and provisioned in candidates) or (setup_num and setup_num in candidates):
                return {"space": row["space"], "project_id": row["project_id"],
                        "session_id": row["session_id"]}
    except Exception:
        return None
    return None


call_store.set_session_resolver(_resolve_session_for_call)

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


def _effective_base():
    """Public URL SignalWire calls back: admin override -> auto-detected -> env."""
    return _CONFIG.effective_base(env_default=base_url)


def _apply_config():
    """Push the effective config into the live process so edits take effect now:
    - SWML_PROXY_URL_BASE env: used by step12 provisioning and the SDK's webhook
      URL generation.
    - SWML_BASIC_AUTH_* env + each agent's `_basic_auth` tuple: the agents both
      EMBED these creds in the webhook URLs they generate AND VALIDATE inbound
      SignalWire requests against them, so both sides must update together.
    """
    base = _effective_base()
    if base:
        os.environ["SWML_PROXY_URL_BASE"] = base
    user, pw = _CONFIG.effective_auth()
    os.environ["SWML_BASIC_AUTH_USER"] = user
    os.environ["SWML_BASIC_AUTH_PASSWORD"] = pw
    for _agent in registered_agents.values():
        try:
            _agent._basic_auth = (user, pw)
        except Exception:  # noqa: BLE001 - never let config application crash a request
            pass


_apply_config()  # apply any persisted overrides at startup

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
    """Capture post_prompt calls that land on the root path."""
    body = await request.body()
    try:
        data = _json.loads(body)
    except Exception:
        data = {}
    agent_name = data.get("app_name") or data.get("agent") or "(root fallback)"
    call_store.STORE.record(agent_name, None, data)
    return JSONResponse({"status": "ok"})

# ---------------------------------------------------------------------------
# Admin dashboard — live post-prompt + sessions view (unlisted, no auth).
# ---------------------------------------------------------------------------

@server.app.get("/admin/calls")
async def admin_calls(request: Request):
    return JSONResponse({"calls": call_store.STORE.all()})


@server.app.get("/admin/sessions")
async def admin_sessions(request: Request):
    return JSONResponse({"sessions": _SESSIONS.admin_snapshot()})


@server.app.delete("/admin/calls")
async def admin_clear_calls(request: Request):
    call_store.STORE.clear()
    return JSONResponse({"status": "cleared"})


@server.app.get("/admin/export")
async def admin_export(request: Request):
    return JSONResponse(
        {"calls": call_store.STORE.all()},
        headers={"Content-Disposition": "attachment; filename=postprompt-calls.json"},
    )


@server.app.get("/admin/config")
async def admin_get_config(request: Request):
    """Current runtime config (public URL + SWAIG basic auth) for the admin page."""
    return JSONResponse(_CONFIG.snapshot(env_default=_effective_base()))


@server.app.post("/admin/config")
async def admin_set_config(request: Request):
    """Save admin-edited config and apply it live. Empty string clears an override
    (falls back to auto-detected/env); omitted keys are left unchanged."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    _CONFIG.update(
        public_base=body.get("public_base"),
        auth_user=body.get("auth_user"),
        auth_password=body.get("auth_password"),
    )
    _apply_config()
    return JSONResponse(_CONFIG.snapshot(env_default=_effective_base()))


@server.app.get("/admin/stream")
async def admin_stream(request: Request):
    """SSE driven by polling the stores' version counters (sync/thread safe)."""
    async def gen():
        last_calls = -1
        last_sessions = -1
        # Prime the client with current state immediately.
        while True:
            if await request.is_disconnected():
                return
            cv = call_store.STORE.version
            sv = _SESSIONS.version
            if cv != last_calls:
                last_calls = cv
                payload = _json.dumps({"calls": call_store.STORE.all()})
                yield f"event: calls\ndata: {payload}\n\n"
            if sv != last_sessions:
                last_sessions = sv
                payload = _json.dumps({"sessions": _SESSIONS.admin_snapshot()})
                yield f"event: sessions\ndata: {payload}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")

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

    @server.app.get("/admin")
    async def admin_page():
        return FileResponse("web/admin.html")

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
async def run_inputs(pillar: str, request: Request):
    if pillar not in PILLAR_REQUIRED_ENV:
        return JSONResponse({"error": "unknown pillar"}, status_code=404)
    required = PILLAR_REQUIRED_ENV[pillar]
    creds = creds_for(request)
    missing = [k for k in required if not creds.get(k)]
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
    creds = creds_for(request)
    env = {**os.environ, **creds, **{str(k): str(v) for k, v in inputs.items()}}

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
async def relay_config(request: Request):
    from python.steps.step12_rest_demo import DEFAULT_REFERENCE, ensure_agent_handler, mint_subscriber_token
    creds = creds_for(request)
    if not creds:
        return JSONResponse({"error": "missing credentials"}, status_code=400)
    session = _SESSIONS.ensure(request.state.session_id)
    try:
        reference = os.environ.get("SUBSCRIBER_REFERENCE", DEFAULT_REFERENCE)
        # Browser calls (audio + video) reach the COMPLETE agent (/step11): it has
        # every capability plus the video avatar, so it's the best showcase. The
        # phone number's own routing is a separate resource and is unaffected.
        destination = await asyncio.to_thread(ensure_agent_handler, _effective_base(), "/step11", None, creds, session, request.state.session_id)
        token, sub_id = await asyncio.to_thread(mint_subscriber_token, reference, None, creds)
        _SESSIONS.save()
        return JSONResponse({"token": token, "destination": destination})
    except Exception as e:  # noqa: BLE001
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

_SESSION_COOKIE = "sw_session"


@server.app.middleware("http")
async def _session_cookie(request: Request, call_next):
    # Auto-detect the public base from the first real (non-local) request so the
    # *.replit.app URL self-populates with no Secret to set. A manual admin
    # override always wins (effective_base checks it first).
    _host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if _host and "localhost" not in _host and not _host.startswith(("127.", "0.0.0.0")):
        _proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        if _CONFIG.set_detected_base(f"{_proto}://{_host}"):
            _apply_config()

    sid = request.cookies.get(_SESSION_COOKIE)
    is_new = not sid or _SESSIONS.get(sid) is None
    if is_new:
        sid = session_store.new_session_id()
    request.state.session_id = sid
    _SESSIONS.ensure(sid)
    _SESSIONS.sweep()
    response = await call_next(request)
    if is_new:
        response.set_cookie(_SESSION_COOKIE, sid, max_age=12 * 60 * 60,
                            httponly=True, samesite="lax", secure=True, path="/")
    return response


def env_fallback_allowed() -> bool:
    """Allow falling back to env/.env creds ONLY when not a Replit deployment."""
    return not os.environ.get("REPLIT_DEPLOYMENT")


def _env_creds() -> dict:
    return {k: os.environ[k] for k in _CRED_KEYS if os.environ.get(k)}


def creds_for(request: Request) -> dict:
    """The caller session's creds, or env creds when running locally (dev)."""
    rec = _SESSIONS.ensure(request.state.session_id)
    if all(rec["creds"].get(k) for k in _CRED_KEYS):
        return dict(rec["creds"])
    if env_fallback_allowed():
        env = _env_creds()
        if all(env.get(k) for k in _CRED_KEYS):
            return env
    return {}


def _credentials_status_for(creds: dict):
    return {
        "configured": all(creds.get(k) for k in _CRED_KEYS),
        "fields": {
            "SIGNALWIRE_PROJECT_ID": bool(creds.get("SIGNALWIRE_PROJECT_ID")),
            "SIGNALWIRE_TOKEN": bool(creds.get("SIGNALWIRE_TOKEN")),
            "SIGNALWIRE_SPACE": creds.get("SIGNALWIRE_SPACE", ""),
        },
    }


@server.app.get("/api/credentials/status")
async def credentials_status(request: Request):
    return JSONResponse(_credentials_status_for(creds_for(request)))


@server.app.post("/api/credentials")
async def set_credentials(request: Request):
    raw = await request.body()
    body = json.loads(raw) if raw else {}
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected a JSON object"}, status_code=400)
    rec = _SESSIONS.ensure(request.state.session_id)
    for k in _CRED_KEYS:
        if k in body:
            value = str(body[k]).strip()
            if value:
                rec["creds"][k] = value
            else:
                rec["creds"].pop(k, None)
    if all(rec["creds"].get(k) for k in _CRED_KEYS):
        _SESSIONS.mark_signed_in(request.state.session_id)
    _SESSIONS.save()
    return JSONResponse(_credentials_status_for(creds_for(request)))

# ---------------------------------------------------------------------------
# Workshop setup — automate phone-number + webhook plumbing via REST.
# Endpoints used by the new onboarding wizard and the per-agent
# "Point my phone number here" buttons.
# ---------------------------------------------------------------------------

VALID_AGENT_ROUTES = {r for r, _, _ in STEPS}


def _require_public_base():
    base = _effective_base()
    if not base:
        raise RuntimeError("no public URL detected; open /admin and set the Public URL, or set SWML_PROXY_URL_BASE")
    return base


def _normalize_route(route: str) -> str:
    if not route or not route.startswith("/"):
        raise RuntimeError("route must start with /")
    if route not in VALID_AGENT_ROUTES:
        raise RuntimeError(f"unknown agent route: {route}")
    return route


def _missing_creds_response(creds):
    if not creds:
        return JSONResponse({"error": "missing credentials"}, status_code=400)
    return None


@server.app.get("/api/setup/status")
async def setup_status(request: Request):
    from python.provisioning import setup_status as _status
    session = _SESSIONS.ensure(request.state.session_id)
    return JSONResponse(_status(creds_for(request), session.get("setup", {}), base_url or ""))


@server.app.get("/api/setup/numbers")
async def setup_numbers(request: Request):
    creds = creds_for(request)
    r = _missing_creds_response(creds)
    if r: return r
    from python.provisioning import list_existing_numbers
    try:
        nums = await asyncio.to_thread(list_existing_numbers, creds, 3)
        return JSONResponse({"numbers": nums})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/search")
async def setup_search(request: Request):
    creds = creds_for(request)
    r = _missing_creds_response(creds)
    if r: return r
    raw = await request.body(); body = json.loads(raw) if raw else {}
    area_code = body.get("area_code")
    if area_code and not str(area_code).isdigit():
        return JSONResponse({"error": "area_code must be digits"}, status_code=400)
    from python.provisioning import search_available
    try:
        nums = await asyncio.to_thread(search_available, creds, str(area_code) if area_code else None, 3)
        return JSONResponse({"numbers": nums, "area_code": area_code or None})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/select")
async def setup_select(request: Request):
    creds = creds_for(request)
    r = _missing_creds_response(creds)
    if r: return r
    try:
        public = _require_public_base()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    raw = await request.body(); body = json.loads(raw) if raw else {}
    route = body.get("route", "/step04")
    try:
        route = _normalize_route(route)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    sid = body.get("sid"); phone_to_buy = body.get("phone_number")
    if not sid and not phone_to_buy:
        return JSONResponse({"error": "either sid or phone_number is required"}, status_code=400)
    from python.provisioning import configure_existing, purchase_and_configure
    session = _SESSIONS.ensure(request.state.session_id)
    try:
        if sid:
            result = await asyncio.to_thread(configure_existing, creds, sid, route, public, request.state.session_id)
        else:
            result = await asyncio.to_thread(purchase_and_configure, creds, phone_to_buy, route, public, request.state.session_id)
        trace = result.pop("_trace", [])
        session["setup"] = result; _SESSIONS.save()
        return JSONResponse({"setup": result, "_trace": trace})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/route")
async def setup_route(request: Request):
    creds = creds_for(request)
    r = _missing_creds_response(creds)
    if r: return r
    try:
        public = _require_public_base()
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    raw = await request.body(); body = json.loads(raw) if raw else {}
    route = body.get("route")
    try:
        route = _normalize_route(route)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    from python.provisioning import repoint_to_route
    session = _SESSIONS.ensure(request.state.session_id)
    try:
        result = await asyncio.to_thread(repoint_to_route, creds, session.get("setup", {}), route, public)
        trace = result.pop("_trace", [])
        session["setup"] = result; _SESSIONS.save()
        return JSONResponse({"setup": result, "_trace": trace})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{e.__class__.__name__}: {e}"}, status_code=502)


@server.app.post("/api/setup/reset")
async def setup_reset(request: Request):
    session = _SESSIONS.ensure(request.state.session_id)
    session["setup"] = {}; _SESSIONS.save()
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
