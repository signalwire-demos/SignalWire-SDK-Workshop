"""
Hardcoded Jokes
---------------
Your first SWAIG function - teaching the AI to tell jokes
from a hardcoded list.

New concepts:
  - FunctionResult: return data from a SWAIG function
  - define_tool(): register a function the AI can call
  - description: tells the AI *when* to use the function (critical!)
  - parameters: what info the AI extracts from conversation
  - function_fillers: phrases spoken while your function runs
"""

import random
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult


JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call a fake noodle? An impasta.",
    "Why don't scientists trust atoms? Because they make up everything.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
    "What did the ocean say to the beach? Nothing, it just waved.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "I used to hate facial hair, but then it grew on me.",
]


class JokeAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="joke-agent-hardcoded", route=route)

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

        # Carrier caller-ID names are location data, not names ("ARIZONA") -
        # shared guard so Buddy never addresses the caller by it.
        from python.steps._caller_identity import add_caller_identity_guard
        add_caller_identity_guard(self)

        # The AI decides when to call this based on the description
        self.define_tool(
            name="tell_joke",
            description=(
                "Tell the caller a funny joke. Use this whenever "
                "someone asks for a joke or humor."
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
        joke = random.choice(JOKES)
        return FunctionResult(f"Here's a joke: {joke}")

    def on_summary(self, summary, raw_data):
        from python.steps._summary_capture import record_call
        record_call(self, raw_data)
