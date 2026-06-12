"""
Step 4: Hello Agent
-------------------
The simplest possible agent - just enough to prove everything works.
Call your number and have a basic conversation with Buddy.

Concepts:
  - AgentBase: the foundation class for every agent
  - add_language(): speech recognition + TTS voice
  - prompt_add_section(): personality and instructions
  - set_post_prompt() + on_summary(): save call data for debugging
"""

from signalwire_agents import AgentBase


class HelloAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="hello-agent", route=route)

        # "rime.spore" is a warm, friendly TTS voice
        self.add_language(
            "English", "en-US", "rime.spore",
            speech_fillers=["Um", "Well"],
        )

        # The AI's personality and instructions
        self.prompt_add_section(
            "Role",
            "You are a friendly assistant named Buddy. "
            "You greet callers warmly, ask how their day is going, "
            "and have a brief pleasant conversation. "
            "Keep your responses short since this is a phone call.",
        )

        # Carrier caller-ID names are location data, not names (an unlisted
        # Arizona cell arrives as "ARIZONA") - shared guard so Buddy never
        # addresses the caller by it.
        from python.steps._caller_identity import add_caller_identity_guard
        add_caller_identity_guard(self)

        # After each call, the AI generates a summary
        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Include what the caller wanted and how the conversation went.",
        )

        from python.steps._postprompt_params import CAPTURE_PARAMS
        self.set_params({**CAPTURE_PARAMS})

    def on_summary(self, summary, raw_data):
        from python.steps._summary_capture import record_call
        record_call(self, raw_data)
