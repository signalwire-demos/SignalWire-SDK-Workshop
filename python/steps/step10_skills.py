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

import json
import os
from datetime import datetime
import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult, DataMap


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

        self.set_params({
            "end_of_speech_timeout": 600,
            "attention_timeout": 15000,
            "attention_timeout_prompt":
                "Are you still there? I can help with weather, "
                "jokes, math, or just chat!",
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
        self._register_weather_datamap()

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

    # -- Weather DataMap ----------------------------------------------------

    def _register_weather_datamap(self):
        weather_dm = (
            DataMap("get_weather")
            .description(
                "Get the current weather for a city. Use this when the caller asks "
                "about weather, temperature, or conditions."
            )
            .parameter("city", "string", "The city to get weather for", required=True)
            # WHY two hops: Open-Meteo splits geocoding from forecast. First call
            # turns the city name into lat/lon; second call fetches current weather.
            .webhook(
                "GET",
                "https://geocoding-api.open-meteo.com/v1/search"
                "?name=${enc:args.city}&count=1&format=json",
            )
            .webhook(
                "GET",
                "https://api.open-meteo.com/v1/forecast"
                "?latitude=${response.results[0].latitude}"
                "&longitude=${response.results[0].longitude}"
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature"
                "&temperature_unit=fahrenheit",
            )
            .output(FunctionResult(
                "Weather in ${args.city}: "
                "${response.current.temperature_2m} degrees Fahrenheit, "
                "humidity ${response.current.relative_humidity_2m} percent. "
                "Feels like ${response.current.apparent_temperature} degrees."
            ))
            .fallback_output(FunctionResult(
                "Sorry, I couldn't get the weather for ${args.city}. "
                "Please check the city name and try again."
            ))
        )

        self.register_swaig_function(weather_dm.to_swaig_function())

    def on_summary(self, summary, raw_data):
        os.makedirs("calls", exist_ok=True)
        call_id = (raw_data or {}).get(
            "call_id", datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        filepath = os.path.join("calls", f"{call_id}.json")
        with open(filepath, "w") as f:
            json.dump(raw_data, f, indent=2, default=str)
        print(f"Call summary saved: {filepath}")
