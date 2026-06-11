"""
Step 10: Built-in Skills
------------------------
Add date/time and math capabilities with just two lines of code.
Skills are pre-built capabilities that ship with the SDK.

New concepts:
  - add_skill(): one line, instant capability
  - "datetime" skill: current time in any timezone
  - "math" skill: calculations, percentages, conversions

Compare the three approaches:
  | Capability | Approach     | Lines | Your Server? |
  |------------|-------------|-------|-------------|
  | Jokes      | define_tool | ~30   | Yes         |
  | Weather    | DataMap     | ~15   | No          |
  | DateTime   | Skill       | 1     | No          |
  | Math       | Skill       | 1     | No          |
"""

import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult


class SkillsAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="skills-agent", route=route)

        self.add_language(
            "English", "en-US", "rime.spore",
            speech_fillers=["Um", "Well", "So"],
            function_fillers=[
                "Let me check on that for you...",
                "One moment while I look that up...",
                "Hang on just a sec...",
            ],
        )

        from python.steps._postprompt_params import CAPTURE_PARAMS
        self.set_params({
            "end_of_speech_timeout": 600,
            "attention_timeout": 15000,
            "attention_timeout_prompt":
                "Are you still there? I can help with weather, "
                "jokes, math, or just chat!",
            **CAPTURE_PARAMS,
        })

        self.add_hints(["Buddy", "weather", "joke", "temperature", "forecast"])

        self.prompt_add_section(
            "Personality",
            "You are Buddy, a cheerful and witty AI phone assistant. "
            "You have a warm, upbeat personality and you genuinely enjoy "
            "helping people. You're a bit of a dad joke enthusiast. "
            "Think of yourself as that friendly neighbor who always "
            "has a joke ready and knows what the weather is like.",
        )

        self.prompt_add_section(
            "Voice Style",
            body="Since this is a phone conversation, follow these rules:",
            bullets=[
                "Keep responses to 1-2 sentences when possible",
                "Use conversational language, not formal or robotic",
                "React to what the caller says before jumping to information",
                "If they laugh at a joke, acknowledge it warmly",
                "Use natural transitions between topics",
            ],
        )

        self.prompt_add_section(
            "Capabilities",
            body="You can help with the following:",
            bullets=[
                "Weather: current conditions for any city worldwide",
                "Jokes: endless supply of dad jokes, always fresh",
                "Date and time: current time in any timezone",
                "Math: calculations, percentages, conversions",
                "General chat: friendly conversation on any topic",
            ],
        )

        self._register_joke_function()
        self._register_weather()

        # NEW: Built-in skills - one line each, zero configuration
        self.add_skill("datetime", {"default_timezone": "America/New_York"})
        self.add_skill("math")

        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Note what the caller asked about (weather, jokes, time, math, etc.) "
            "and how the interaction went.",
        )

    # -- Dad jokes ---------------------------------------------------------

    def _register_joke_function(self):
        self.define_tool(
            name="tell_joke",
            description=(
                "Tell the caller a funny dad joke. Use this whenever "
                "someone asks for a joke or humor."
            ),
            parameters={"type": "object", "properties": {}},
            handler=self.on_tell_joke,
            fillers={
                "en-US": [
                    "Let me think of a good one...",
                    "Oh, I've got one for you...",
                    "Here comes a good one...",
                ],
            },
        )

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

    # -- Weather (server-side SWAIG tool, runs on our server) ----------------

    def _register_weather(self):
        # Server-side define_tool, NOT a serverless DataMap: a real workshop call
        # proved SignalWire's DataMap engine left every ${...} empty for this
        # function. Fetching + formatting here is deterministic. See _weather.py.
        from python.steps._weather import register_weather_tool
        register_weather_tool(self)

    def on_summary(self, summary, raw_data):
        from python.steps._summary_capture import record_call
        record_call(self, raw_data)
