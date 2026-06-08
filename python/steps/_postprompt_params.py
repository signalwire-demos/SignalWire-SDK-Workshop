# python/steps/_postprompt_params.py
"""Shared post-prompt configuration for every workshop agent.

The /admin dashboard showcases the full post-prompt feature set: it renders the
conversation transcript, the tool/DataMap calls, and the call metadata. Those
require the agent to opt in to sending that data after the call:

  - swaig_post_conversation: includes call_log / raw_call_log (transcript + tools)
  - swaig_post_swml_vars:    includes SWMLVars (to / from on the Meta tab)

Keeping both flags here means every agent enables identical capture from one
place, instead of copy-pasting into each set_params().
"""

# Merge these into each agent's set_params() call.
CAPTURE_PARAMS = {
    "swaig_post_conversation": True,
    "swaig_post_swml_vars": True,
}
