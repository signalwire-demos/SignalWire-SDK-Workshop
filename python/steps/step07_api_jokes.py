"""
Step 7: Live API Jokes
----------------------
Replace hardcoded jokes with fresh ones from icanhazdadjoke.com.
Every call returns a different joke.

New concepts:
  - Calling external APIs from a SWAIG function handler
  - Graceful error handling when APIs fail
"""

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

        from python.steps._postprompt_params import CAPTURE_PARAMS
        self.set_params({**CAPTURE_PARAMS})

    def on_tell_joke(self, args, raw_data):
        # WHY: removes the API Ninjas key dependency so attendees skip a prereq.
        try:
            resp = requests.get(
                "https://icanhazdadjoke.com/",
                headers={"Accept": "application/json", "User-Agent": "signalwire-agents-sdk-workshop"},
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
        from python.steps._summary_capture import record_call
        record_call(self, raw_data)
