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

import json
import os
from datetime import datetime
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

        # After each call, the AI generates a summary
        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Include what the caller wanted and how the conversation went.",
        )

    def on_summary(self, summary, raw_data):
        """Save post-prompt data to calls/ for debugging.

        Upload JSON files to https://postpromptviewer.signalwire.io/
        """
        os.makedirs("calls", exist_ok=True)
        call_id = (raw_data or {}).get(
            "call_id", datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        filepath = os.path.join("calls", f"{call_id}.json")
        with open(filepath, "w") as f:
            json.dump(raw_data, f, indent=2, default=str)
        print(f"Call summary saved: {filepath}")
