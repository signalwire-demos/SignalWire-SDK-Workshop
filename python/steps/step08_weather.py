"""
Step 8: Weather DataMap + Jokes
-------------------------------
Add weather lookups using DataMap - a serverless approach where
SignalWire calls the Open-Meteo API directly, not through your server.

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
