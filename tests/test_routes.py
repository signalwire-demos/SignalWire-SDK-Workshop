"""
Smoke tests for the Chicago Roadshow harness.

These tests cover the harness only; they do NOT call the real SignalWire API.
For /run/* tests, bogus creds are injected so the subprocess fails auth
predictably and we can assert on the exit line.

Run from the project root:
    pytest tests/test_routes.py -v
"""

import json
import os
import subprocess
import sys
import time

import pytest
import requests

# Use a non-default port so tests never conflict with a dev server on :5000.
_TEST_PORT = int(os.environ.get("TEST_SERVER_PORT", "5099"))
BASE_URL = os.environ.get("TEST_BASE_URL", f"http://127.0.0.1:{_TEST_PORT}")

# SDK enforces basic auth on all agent routes.
# These match the defaults set by replit_setup.py; override via env if needed.
_AGENT_AUTH = (
    os.environ.get("SWML_BASIC_AUTH_USER", "workshop"),
    os.environ.get("SWML_BASIC_AUTH_PASSWORD", "password"),
)


@pytest.fixture(scope="module", autouse=True)
def _server():
    # WHY scope=module: starting the server once per test module is far
    # faster than per-test. Tests are read-only on server state.
    if "TEST_BASE_URL" in os.environ:
        yield
        return
    # WHY REPLIT_DEPLOYMENT=1: run the server in its multi-tenant deployment
    # mode so env/.env credential fallback is disabled. This is what the
    # credential-isolation tests validate; without it a local .env would make
    # every fresh session look "configured" and mask cross-session leaks.
    env = {**os.environ, "PORT": str(_TEST_PORT), "PYTHONUNBUFFERED": "1",
           "REPLIT_DEPLOYMENT": "1"}
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/config", timeout=1)
            if r.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.3)
    else:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        raise RuntimeError(
            "server did not start in time\n" + out.decode("utf-8", errors="replace")
        )
    yield
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("route", ["/step04", "/step06", "/step07", "/step08", "/step09", "/step10", "/step11"])
def test_step_route_returns_swml(route):
    # Agent routes require basic auth (SDK middleware); /config and / do not.
    r = requests.get(f"{BASE_URL}{route}/", auth=_AGENT_AUTH, timeout=10)
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert "version" in body
    assert "sections" in body and "main" in body["sections"]


def test_landing_page():
    r = requests.get(f"{BASE_URL}/", timeout=5)
    assert r.status_code == 200
    text = r.text
    assert "Chicago Roadshow" in text or "Workshop" in text or "SignalWire" in text


@pytest.mark.parametrize("pillar,required_subset", [
    ("rest", {"SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE"}),
])
def test_run_inputs_endpoint(pillar, required_subset):
    r = requests.get(f"{BASE_URL}/run/{pillar}/inputs", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["pillar"] == pillar
    assert isinstance(data["required"], list)
    assert required_subset.issubset(set(data["required"]))
    assert isinstance(data["missing"], list)


def test_run_inputs_unknown_pillar():
    r = requests.get(f"{BASE_URL}/run/bogus/inputs", timeout=5)
    assert r.status_code == 404


def test_run_rest_with_bogus_creds_streams_an_exit():
    payload = {"inputs": {
        "SIGNALWIRE_PROJECT_ID": "bogus",
        "SIGNALWIRE_TOKEN": "bogus",
        "SIGNALWIRE_SPACE": "bogus.signalwire.com",
        "SMS_FROM": "+15555550100",
        "SMS_TO": "+15555550101",
    }}
    r = requests.post(f"{BASE_URL}/run/rest", json=payload, timeout=5)
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert run_id

    saw_exit = False
    saw_any_output = False
    deadline = time.time() + 20
    with requests.get(
        f"{BASE_URL}/run/rest/stream/{run_id}",
        stream=True,
        timeout=20,
    ) as s:
        for raw in s.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                break
            if not raw or not raw.startswith("data:"):
                continue
            saw_any_output = True
            payload_str = raw[len("data:"):].strip()
            try:
                msg = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            if msg.get("event") == "exit":
                saw_exit = True
                break

    assert saw_any_output, "stream produced no data lines"
    assert saw_exit, "subprocess never emitted an exit event"


def test_landing_has_wizard_milestones():
    """Onboarding state ships with the 3 wizard milestones and the wizard card."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    assert r.status_code == 200
    text = r.text
    # Theme & state-machine signal
    assert "chicago2026.onboardingComplete" in text, "state machine missing"
    assert "--sw-cyan" in text and "--sw-magenta" in text, "theme variables missing"
    # Wizard wiring
    assert "MILESTONES" in text and "renderMilestones" in text
    assert "renderMilestoneCreds" in text and "renderMilestoneDone" in text
    # No green leftovers
    assert "#00c853" not in text, "green sneaked back in - use --sw-cyan"


def test_landing_has_workshop_renderer():
    """Workshop state and the Call Fabric pipeline runtime are present."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    assert "renderWorkshop" in text
    assert "renderTimeline" in text
    assert "renderStepSection" in text
    # The Phase-2 redesign replaced the per-pillar "Run" SSE subprocess demo
    # (runPillar / EventSource(`/run/...`)) with the interactive Call Fabric
    # pipeline diagram driven by setCfStage. The orphaned runPillar machinery
    # was removed; assert the live driver is present instead.
    assert "runPillar" not in text, "orphaned pillar SSE machinery must stay removed"
    assert "function setCfStage" in text, "Call Fabric stage driver missing"


def test_landing_references_step_routes():
    """All seven agent routes are referenced in STEPS_META."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    for route in ["/step04", "/step06", "/step07", "/step08", "/step09", "/step10", "/step11"]:
        assert f'"{route}"' in text, f"missing route {route}"


def test_step12_main_returns_2_without_creds(monkeypatch):
    # WHY in-process: this checks the missing-creds guard without any network.
    for k in ("SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE"):
        monkeypatch.delenv(k, raising=False)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from python.steps import step12_rest_demo
    assert hasattr(step12_rest_demo, "ensure_agent_handler")
    assert hasattr(step12_rest_demo, "mint_subscriber_token")
    assert step12_rest_demo.main() == 2


def test_relay_pillar_run_inputs_gone():
    # The relay subprocess pillar was replaced by the browser click-to-call.
    r = requests.get(f"{BASE_URL}/run/relay/inputs", timeout=5)
    assert r.status_code == 404


def test_relay_config_returns_clean_error_without_creds():
    # No live creds in CI, so this must report a handled error, never a 500.
    r = requests.get(f"{BASE_URL}/api/relay/config", timeout=15)
    assert r.status_code != 500
    data = r.json()
    assert "token" in data or "error" in data


def test_buddy_video_client_js_served():
    # buddy-video.js is the single browser-call client (relay-client.js retired).
    r = requests.get(f"{BASE_URL}/static/buddy-video.js", timeout=5)
    assert r.status_code == 200
    body = r.text
    assert "SignalWire.SignalWire" in body
    assert ".dial(" in body
    assert "requestPermissions" in body


def test_static_assets_no_cache_and_unversioned():
    # /static is served no-cache so a redeploy never hands a returning attendee a
    # stale bundle (replaces the old ?v= query-string cache-buster on the script).
    r = requests.get(f"{BASE_URL}/static/buddy-video.js", timeout=5)
    assert "no-cache" in r.headers.get("cache-control", "").lower()
    landing = requests.get(f"{BASE_URL}/", timeout=5).text
    assert "/static/buddy-video.js?v=" not in landing
    assert '<script src="/static/buddy-video.js">' in landing


def test_html_documents_are_no_cache():
    # The / and /admin HTML documents must ALSO be no-cache. Otherwise a returning
    # attendee gets a stale cached index that serves old inline JS (e.g. a pre-fix
    # post-prompt modal that won't open). /static was already no-cache; the HTML
    # documents that load it must be too.
    for path in ("/", "/admin"):
        r = requests.get(f"{BASE_URL}{path}", timeout=5)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "no-cache" in r.headers.get("cache-control", "").lower(), \
            f"{path} should send Cache-Control: no-cache"


def test_landing_loads_browser_sdk_and_client():
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    # SDK pinned to v4; the audio-only relay-client.js is no longer loaded.
    assert "cdn.signalwire.com/@signalwire/js@4.0.0-rc.0" in text
    assert "/static/relay-client.js" not in text
    assert "/static/buddy-video.js" in text


def test_landing_has_call_fabric_diagram():
    # The two static "Bonus" cards were replaced by the interactive Call Fabric
    # pipeline diagram with a single browser-call button.
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    assert 'id="buddy-call-btn"' in text
    assert 'class="cf-pipeline"' in text
    assert 'data-cf-node="browser"' in text
    assert "function revealCfNode" in text
    # The retired audio-only relay wiring is gone.
    assert "RelayCall" not in text


def test_credentials_status_shape():
    r = requests.get(f"{BASE_URL}/api/credentials/status", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "configured" in data
    assert "fields" in data
    assert set(data["fields"]) == {"SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE"}


def _session_cookies(response):
    # The session cookie is marked Secure (correct for production HTTPS), so
    # requests will not auto-resend it over the plain-HTTP test transport.
    # Carry it forward explicitly so a test can act as one consistent browser.
    sid = response.cookies.get("sw_session")
    assert sid, "server did not set an sw_session cookie"
    return {"sw_session": sid}


def test_credentials_shared_across_pillars_within_a_session():
    # Within ONE browser session, creds entered once must reach BOTH pillars:
    # the REST inputs endpoint and the credentials status endpoint. The
    # multi-tenant refactor scopes creds to the session cookie instead of
    # mutating global os.environ.
    r = requests.post(f"{BASE_URL}/api/credentials", json={
        "SIGNALWIRE_PROJECT_ID": "test-project",
        "SIGNALWIRE_TOKEN": "test-token",
        "SIGNALWIRE_SPACE": "test.signalwire.com",
    }, timeout=5)
    assert r.status_code == 200
    assert r.json()["configured"] is True
    jar = _session_cookies(r)

    # REST pillar inputs (session-scoped) now report nothing missing.
    inputs = requests.get(f"{BASE_URL}/run/rest/inputs", cookies=jar, timeout=5).json()
    assert inputs["missing"] == []

    status = requests.get(f"{BASE_URL}/api/credentials/status", cookies=jar, timeout=5).json()
    assert status["configured"] is True
    assert status["fields"]["SIGNALWIRE_SPACE"] == "test.signalwire.com"
    assert status["fields"]["SIGNALWIRE_TOKEN"] is True


def test_credentials_isolated_across_sessions():
    # The point of the refactor: creds set in one session must NOT leak into a
    # different session. Each cookie jar is a distinct browser.
    ra = requests.post(f"{BASE_URL}/api/credentials", json={
        "SIGNALWIRE_PROJECT_ID": "PXA",
        "SIGNALWIRE_TOKEN": "PTA",
        "SIGNALWIRE_SPACE": "a.signalwire.com",
    }, timeout=5)
    jar_a = _session_cookies(ra)

    # A brand-new request with no cookie is a fresh session.
    status_b = requests.get(f"{BASE_URL}/api/credentials/status", timeout=5).json()
    assert status_b["configured"] is False
    assert status_b["fields"]["SIGNALWIRE_SPACE"] != "a.signalwire.com"

    status_a = requests.get(f"{BASE_URL}/api/credentials/status", cookies=jar_a, timeout=5).json()
    assert status_a["configured"] is True
    assert status_a["fields"]["SIGNALWIRE_SPACE"] == "a.signalwire.com"
