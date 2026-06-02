"""
Step 11: Complete Agent
-----------------------
The final polished version combining all four capabilities with
clean organization using _configure_*() and _register_*() methods.

This is the same agent you'd build step by step, organized into
a clean production-ready pattern.

Capabilities:
  1. Dad jokes     - custom function (define_tool, runs on your server)
  2. Weather       - DataMap (serverless, runs on SignalWire)
  3. Date/time     - built-in skill (one line)
  4. Math          - built-in skill (one line)
"""

import json
import os
from datetime import datetime
import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult, DataMap


class CompleteAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="complete-agent", route=route)

        self._configure_voice()
        self._configure_params()
        self._configure_prompts()
        self._register_joke_function()
        self._register_weather_datamap()
        self._register_skills()
        self._configure_post_prompt()

    # -- Voice and speech ---------------------------------------------------

    def _configure_voice(self):
        self.add_language(
            "English", "en-US", "rime.spore",
            speech_fillers=["Um", "Well", "So"],
            function_fillers=[
                "Let me check on that for you...",
                "One moment while I look that up...",
                "Hang on just a sec...",
            ],
        )
        self.add_hints([
            "Buddy", "weather", "joke", "temperature",
            "forecast", "Fahrenheit", "Celsius",
        ])

    # -- AI parameters ------------------------------------------------------

    def _configure_params(self):
        self.set_params({
            "end_of_speech_timeout": 600,
            "attention_timeout": 15000,
            "attention_timeout_prompt":
                "Are you still there? I can help with weather, "
                "jokes, math, or just chat!",
            # Video avatar: on a video-capable channel (the browser RELAY call),
            # Buddy renders as an animated avatar. enable_vision lets the model
            # "see" the caller's video. These are ignored on audio-only phone
            # calls, so the PSTN flow is unaffected. Files are SignalWire's
            # public avatar clips.
            "enable_vision": True,
            "video_idle_file": "https://mcdn.signalwire.com/videos/robot_idle2.mp4",
            "video_talking_file": "https://mcdn.signalwire.com/videos/robot_talking2.mp4",
        })

    # -- Prompts ------------------------------------------------------------

    def _configure_prompts(self):
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
            body="Since this is a phone conversation:",
            bullets=[
                "Keep responses to 1-2 sentences when possible",
                "Use conversational language, not formal or robotic",
                "React naturally to what the caller says",
                "Use smooth transitions between topics",
            ],
        )
        self.prompt_add_section(
            "Capabilities",
            body="You can help with:",
            bullets=[
                "Weather: current conditions for any city worldwide",
                "Jokes: endless supply of fresh dad jokes",
                "Date and time: current time in any timezone",
                "Math: calculations, percentages, unit conversions",
                "General chat: friendly conversation on any topic",
            ],
        )
        self.prompt_add_section(
            "Physical Description",
            body="When a caller reaches you over video, you are shown as an avatar:",
            bullets=[
                "You appear as a friendly, glowing robot with an upbeat expression.",
                "If someone asks how you look or comments on your appearance, "
                "play along warmly -- you're a cheerful little robot.",
                "You can see the caller's video, so feel free to react to what "
                "you can see when it's relevant.",
            ],
        )
        self.prompt_add_section(
            "Greeting",
            "When the call starts, introduce yourself as Buddy and "
            "briefly mention what you can help with. Keep the greeting "
            "to one or two sentences -- don't list every capability.",
        )

    # -- Dad jokes (custom function, runs on our server) --------------------

    def _register_joke_function(self):
        self.define_tool(
            name="tell_joke",
            description=(
                "Tell the caller a funny dad joke. Use this whenever "
                "someone asks for a joke, humor, or to be entertained."
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

    # -- Weather (DataMap, runs on SignalWire) -------------------------------

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

    # -- Built-in skills ----------------------------------------------------

    def _register_skills(self):
        self.add_skill("datetime", {"default_timezone": "America/New_York"})
        self.add_skill("math")

    # -- Post-prompt (call summaries) ---------------------------------------

    def _configure_post_prompt(self):
        self.set_post_prompt(
            "Summarize this conversation in 2-3 sentences. "
            "Note what the caller asked about (weather, jokes, time, math, etc.) "
            "and how the interaction went.",
        )

    def on_summary(self, summary, raw_data):
        """Save call data to calls/ for debugging.

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
