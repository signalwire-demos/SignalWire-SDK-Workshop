# python/steps/_caller_identity.py
"""Shared caller-ID-name prompt guard for every workshop agent.

SignalWire exposes the call's CNAM string to the model as
prompt_vars.caller_id_name. Numbers without a CNAM listing (most cell
phones) get carrier location data instead of a name, so a caller from an
unlisted Arizona number arrives with the literal name "ARIZONA" and the AI
starts addressing them as "Arizona". There is no ai.params switch that
suppresses the variable, so the fix is an explicit prompt instruction.

Like _postprompt_params.py, keeping the text here means every agent ships
the identical guard from one place:

  flat-prompt agents:        add_caller_identity_guard(self)
  contexts agents (step11):  ctx.add_section("Caller Identity", CALLER_ID_GUIDELINE)
"""

CALLER_ID_GUIDELINE = (
    "The caller ID name attached to this call is carrier billing data, not "
    "the caller's actual name. For unlisted numbers it is usually a state, "
    "city, or company (for example 'ARIZONA'). Never address the caller by "
    "it, never assume their name or location from it, and never mention it. "
    "If you need the caller's name, ask for it."
)


def add_caller_identity_guard(agent):
    """Append the guard as its own prompt section on a flat-prompt agent."""
    agent.prompt_add_section("Caller Identity", CALLER_ID_GUIDELINE)
