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

import requests
from signalwire_agents import AgentBase, SwaigFunctionResult as FunctionResult


class CompleteAgent(AgentBase):
    def __init__(self, route="/"):
        super().__init__(name="complete-agent", route=route)

        self._configure_voice()
        self._configure_params()
        self._configure_prompts()
        self._register_joke_function()
        self._register_weather()
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
        from python.steps._postprompt_params import CAPTURE_PARAMS
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
            **CAPTURE_PARAMS,
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

    # -- Weather (server-side SWAIG tool, runs on our server) ----------------

    def _register_weather(self):
        # Server-side define_tool, NOT a serverless DataMap: a real workshop call
        # proved SignalWire's DataMap engine left every ${...} empty for this
        # function. Fetching + formatting here is deterministic. See _weather.py.
        from python.steps._weather import register_weather_tool
        register_weather_tool(self)

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

    def on_swml_request(self, request_data=None, callback_path=None, request=None):
        """Stamp the workshop session id into global_data so post-prompt
        capture can correlate this call back to the attendee's session.

        The per-session SWML handler URL carries ?sid=<session_id>; we read it
        from whichever source the SDK provides and merge it into global_data,
        which rides through the call and is echoed in the post-prompt body.
        """
        sid = None
        if isinstance(request_data, dict):
            sid = request_data.get("sid")
        if not sid and request is not None:
            qp = getattr(request, "query_params", {}) or {}
            sid = qp.get("sid") if hasattr(qp, "get") else None
        if not sid:
            return None
        return {"global_data": {"workshop_session_id": sid}}

    def on_summary(self, summary, raw_data):
        from python.steps._summary_capture import record_call
        record_call(self, raw_data)
