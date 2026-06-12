# tests/test_caller_identity_guard.py
"""Every workshop agent must tell the model to ignore the caller-ID name.

SignalWire builds prompt_vars.caller_id_name from the call's CNAM channel
variable. Numbers without a CNAM listing (most cell phones) get carrier
location data instead, so a caller from an unlisted Arizona number arrives
with the literal name "ARIZONA" and the AI starts addressing them as
"Arizona". The SWML ai.params surface has no switch to suppress the
variable, so the countermeasure is an explicit prompt guideline on every
agent (shared from python/steps/_caller_identity.py, mirroring how
_postprompt_params.py shares capture flags).
"""
import sys

sys.path.insert(0, ".")

import main  # noqa: E402  (builds + registers all agents; server.run() is guarded)
from python.steps._caller_identity import CALLER_ID_GUIDELINE  # noqa: E402


def test_guideline_is_json_safe_marker():
    # The assertion below searches the raw rendered JSON, which only works
    # while the guideline contains no double quotes or backslashes.
    assert '"' not in CALLER_ID_GUIDELINE and "\\" not in CALLER_ID_GUIDELINE


def test_every_agent_swml_contains_caller_identity_guard():
    assert main.registered_agents, "no agents registered"
    for route, agent in main.registered_agents.items():
        swml = agent._render_swml()
        assert CALLER_ID_GUIDELINE in swml, f"{route} is missing the caller-ID guard"
