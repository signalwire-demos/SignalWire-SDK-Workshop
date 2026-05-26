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
    env = {**os.environ, "PORT": str(_TEST_PORT), "PYTHONUNBUFFERED": "1"}
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
    ("rest", {"SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE", "SMS_FROM", "SMS_TO"}),
    ("relay", {"SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN"}),
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
    """Onboarding state ships with 4 milestones and the wizard card."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    assert r.status_code == 200
    text = r.text
    # Theme & state-machine signal
    assert "chicago2026.onboardingComplete" in text, "state machine missing"
    assert "--sw-cyan" in text and "--sw-magenta" in text, "theme variables missing"
    # Wizard wiring
    assert "MILESTONES" in text and "renderMilestones" in text
    assert "renderMilestone1" in text and "renderMilestone4" in text
    # No green leftovers
    assert "#00c853" not in text, "green sneaked back in — use --sw-cyan"


def test_landing_has_workshop_renderer():
    """Workshop state and pillar runtime are present."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    assert "renderWorkshop" in text
    assert "renderTimeline" in text
    assert "renderActiveDetail" in text
    assert "runPillar" in text, "pillar SSE machinery missing"
    assert 'EventSource(`/run/' in text, "EventSource wiring missing"


def test_landing_references_step_routes():
    """All seven agent routes are referenced in STEPS_META."""
    r = requests.get(f"{BASE_URL}/", timeout=5)
    text = r.text
    for route in ["/step04", "/step06", "/step07", "/step08", "/step09", "/step10", "/step11"]:
        assert f'"{route}"' in text, f"missing route {route}"
