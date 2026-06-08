"""
Step 8: Weather DataMap + Jokes
-------------------------------
Add weather lookups using DataMap - a serverless approach where
SignalWire calls the wttr.in weather API directly, not through your server.

New concepts:
  - DataMap: declare an API call, SignalWire executes it
  - .parameter(): tell the AI what to extract from conversation
  - .webhook(): the HTTP request SignalWire will make
  - .output() / .fallback_output(): response templates with ${} variables
  - Key difference: define_tool runs on YOUR server, DataMap runs on SIGNALWIRE
"""

import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult


class WeatherJokeAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="weather-joke-agent", route=route)

        self.add_language(
            "English", "en-US", "rime.spore",
            speech_fillers=["Um", "Well"],
            function_fillers=[
                "Let me check on that...",
                "One moment...",
            ],
        )

        self.prompt_add_section(
            "Role",
            "You are a friendly assistant named Buddy. "
            "You help people with weather information and tell great jokes. "
            "Keep your responses short since this is a phone call.",
        )

        self.prompt_add_section(
            "Guidelines",
            body="Follow these guidelines:",
            bullets=[
                "When someone asks about weather, use the get_weather function",
                "When someone asks for a joke, use the tell_joke function",
                "Be warm, friendly, and conversational",
            ],
        )

        self._register_joke_function()
        self._register_weather()

        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Note what the caller asked about (weather, jokes, etc.) "
            "and how the interaction went.",
        )

        from python.steps._postprompt_params import CAPTURE_PARAMS
        self.set_params({**CAPTURE_PARAMS})

    # -- Dad jokes (runs on our server) ------------------------------------

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
                "en-US": ["Let me think of a good one..."],
            },
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
