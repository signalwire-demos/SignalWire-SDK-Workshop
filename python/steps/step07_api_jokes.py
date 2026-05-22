"""
Step 7: Live API Jokes
----------------------
Replace hardcoded jokes with fresh ones from icanhazdadjoke.com.
Every call returns a different joke.

New concepts:
  - Calling external APIs from a SWAIG function handler
  - Graceful error handling when APIs fail
"""

import json
import os
from datetime import datetime
import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult


class JokeAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="joke-agent-api", route=route)

        self.add_language(
            "English", "en-US", "rime.spore",
            speech_fillers=["Um", "Well"],
            function_fillers=["Let me think of a good one..."],
        )

        self.prompt_add_section(
            "Role",
            "You are a friendly assistant named Buddy. "
            "You love telling jokes and making people laugh. "
            "Keep your responses short since this is a phone call.",
        )

        self.prompt_add_section(
            "Guidelines",
            body="Follow these guidelines:",
            bullets=[
                "When someone asks for a joke, use the tell_joke function",
                "After telling a joke, pause for a reaction before offering another",
                "Be enthusiastic and have fun with it",
            ],
        )

        self.define_tool(
            name="tell_joke",
            description=(
                "Tell the caller a funny dad joke. Use this whenever "
                "someone asks for a joke, humor, or to be entertained."
            ),
            parameters={"type": "object", "properties": {}},
            handler=self.on_tell_joke,
        )

        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Note which jokes were told and how the caller reacted.",
        )

    def on_tell_joke(self, args, raw_data):
        # WHY: removes the API Ninjas key dependency so attendees skip a prereq.
        try:
            resp = requests.get(
                "https://icanhazdadjoke.com/",
                headers={"Accept": "application/json", "User-Agent": "chicago-roadshow-2026"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            joke = data.get("joke")
            if not joke:
                return FunctionResult("I couldn't find a joke this time. Try again!")
            return FunctionResult(f"Here's a dad joke: {joke}")
        except requests.RequestException:
            return FunctionResult("My joke service is taking a break. Try again in a moment!")

    def on_summary(self, summary, raw_data):
        os.makedirs("calls", exist_ok=True)
        call_id = (raw_data or {}).get(
            "call_id", datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        filepath = os.path.join("calls", f"{call_id}.json")
        with open(filepath, "w") as f:
            json.dump(raw_data, f, indent=2, default=str)
        print(f"Call summary saved: {filepath}")
