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

import json
import os
from datetime import datetime
import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult, DataMap


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
        self._register_weather_datamap()

        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Note what the caller asked about (weather, jokes, etc.) "
            "and how the interaction went.",
        )

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

    # -- Weather (runs on SignalWire via DataMap) ---------------------------

    def _register_weather_datamap(self):
        # WHY one webhook: DataMap runs multiple webhooks as sequential
        # FALLBACKS, not a pipeline -- there's no way to feed one webhook's
        # response into the next webhook's request. So we use wttr.in, which
        # takes the city name directly (no separate geocoding hop) and needs
        # no API key, keeping the workshop prerequisite-free.
        weather_dm = (
            DataMap("get_weather")
            .description(
                "Get the current weather for a city. Use this when the caller asks "
                "about weather, temperature, or conditions."
            )
            .parameter("city", "string", "The city to get weather for", required=True)
            .webhook("GET", "https://wttr.in/${enc:args.city}?format=j1")
            .output(FunctionResult(
                "Weather in ${args.city}: "
                "${response.current_condition[0].weatherDesc[0].value}, "
                "${response.current_condition[0].temp_F} degrees Fahrenheit, "
                "humidity ${response.current_condition[0].humidity} percent. "
                "Feels like ${response.current_condition[0].FeelsLikeF} degrees."
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
