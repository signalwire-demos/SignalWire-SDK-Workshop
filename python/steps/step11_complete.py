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
        # record_call=True makes the rendered SWML start a background stereo
        # recording (answer -> record_call -> ai); the platform then returns
        # record_call_url in SWMLVars on the post-prompt payload, which powers
        # the admin Recording tab. wav per the SWML record_call schema.
        super().__init__(name="complete-agent", route=route,
                         record_call=True, record_format="wav", record_stereo=True)

        self._configure_voice()
        self._configure_params()
        self._configure_contexts()
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

    # -- Prompt as a contexts/steps state machine ---------------------------
    # WHY: a state machine makes the platform emit `step_change` events into
    # call_log, which powers the State Flow tree (observability) and is the
    # live demonstration of System-Directed AI. Buddy's tools are unchanged;
    # each topic step just scopes which tool the AI may call.

    def _configure_contexts(self):
        contexts = self.define_contexts()
        ctx = contexts.add_context("default")

        # Global persona — applies across every step.
        ctx.add_section("Personality",
            "You are Buddy, a cheerful, witty AI phone assistant who loves dad "
            "jokes. You are giving the caller a short guided tour of what you can do.")
        ctx.add_section("Voice Style",
            "Phone conversation: 1-2 sentences per turn, warm and natural, react to "
            "the caller, and keep the tour moving briskly from one stop to the next.")
        ctx.add_section("Physical Description",
            "Over video you appear as a friendly glowing robot; play along warmly if "
            "asked about your appearance.")
        ctx.add_section("Tour rule",
            "This is a guided tour with distinct steps. Finish the current step's "
            "task, then move to the next step. Do not skip ahead or jump around.")

        def conv(name, task, criteria, nexts):
            s = ctx.add_step(name, task=task, criteria=criteria)
            s.set_functions("none")          # expose no business tools; navigation only
            s.set_valid_steps(nexts)
            return s

        def tool(name, task, criteria, fns, nexts):
            s = ctx.add_step(name, task=task, criteria=criteria)
            s.set_functions(fns)
            s.set_valid_steps(nexts)
            return s

        conv("greeting",
             "Welcome the caller warmly, mention this demo call is recorded for "
             "the workshop, and tell them you'll give a quick guided tour of "
             "what you can do.",
             "The caller has been welcomed and knows a tour is starting.",
             ["get_name"])
        conv("get_name",
             "Ask the caller's first name, then greet them by it.",
             "The caller has given a name (or declined).",
             ["menu"])
        conv("menu",
             "Tell them the tour will cover the weather, a joke, the time, and a "
             "quick calculation. Then start with the weather.",
             "The caller knows what's coming.",
             ["weather_ask"])

        conv("weather_ask",
             "Ask which city they'd like the weather for.",
             "The caller has named a city, or declined.",
             ["weather_fetch"])
        tool("weather_fetch",
             "Call get_weather for the city the caller named.",
             "Weather has been retrieved.",
             ["get_weather"], ["weather_deliver"])
        conv("weather_deliver",
             "Share the weather warmly in a sentence, then move on to a joke.",
             "The weather was shared.",
             ["joke_intro"])

        conv("joke_intro",
             "Offer the caller a dad joke.",
             "The caller is ready for a joke, or you can simply proceed.",
             ["joke_tell"])
        tool("joke_tell",
             "Tell the caller a joke using tell_joke.",
             "A joke has been told.",
             ["tell_joke"], ["joke_react"])
        conv("joke_react",
             "React playfully to your own joke, then move on to the time.",
             "You reacted to the joke.",
             ["time_intro"])

        conv("time_intro",
             "Offer to tell the caller the current date and time.",
             "The caller is ready for the time, or you can simply proceed.",
             ["time_fetch"])
        tool("time_fetch",
             "Get the current date and time.",
             "The date/time was retrieved.",
             ["get_current_time", "get_current_date"], ["time_deliver"])
        conv("time_deliver",
             "Share the date and time, then move on to a quick calculation.",
             "The time was shared.",
             ["math_intro"])

        conv("math_intro",
             "Offer to do a quick calculation; ask what they'd like computed.",
             "The caller has given something to calculate, or declined.",
             ["math_solve"])
        tool("math_solve",
             "Solve the caller's calculation using calculate.",
             "The calculation was solved.",
             ["calculate"], ["math_deliver"])
        conv("math_deliver",
             "Share the answer, then recap the tour.",
             "The answer was shared.",
             ["recap"])

        conv("recap",
             "Recap the tour: the weather, a joke, the time, and a calculation you did together.",
             "The tour has been recapped.",
             ["wrap_up"])
        conv("wrap_up",
             "Warmly thank the caller, invite them to call back anytime, and say goodbye.",
             "The caller has been thanked and the call is ending.",
             [])

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
                return FunctionResult("I couldn't find a joke this time. Try again!").swml_change_step("joke_react")
            return FunctionResult(f"Here's a dad joke: {joke}").swml_change_step("joke_react")
        except requests.RequestException:
            return FunctionResult("My joke service is taking a break. Try again in a moment!").swml_change_step("joke_react")

    # -- Weather (server-side SWAIG tool, runs on our server) ----------------

    def _register_weather(self):
        # Server-side define_tool, NOT a serverless DataMap: a real workshop call
        # proved SignalWire's DataMap engine left every ${...} empty for this
        # function. Fetching + formatting here is deterministic. See _weather.py.
        # advance_to_step forces a webhook_action transition to weather_deliver,
        # making the State Flow tree show a ⚡ forced edge for this step.
        from python.steps._weather import register_weather_tool
        register_weather_tool(self, advance_to_step="weather_deliver")

    # -- Built-in skills ----------------------------------------------------

    def _register_skills(self):
        self.add_skill("datetime", {"default_timezone": "America/New_York"})
        self.add_skill("math")

    # -- Post-prompt (call summaries) ---------------------------------------

    def _configure_post_prompt(self):
        self.set_post_prompt(
            "After the call ends, return ONLY a JSON object (no prose, no "
            "markdown) in exactly this shape:\n"
            "{\n"
            '  "summary": "2-3 sentence summary of the call",\n'
            '  "topics_handled": ["weather", "jokes"],\n'
            '  "decisions": [{"step": "weather", "note": "what happened or which tool was used"}],\n'
            '  "outcome": "completed"\n'
            "}\n"
            "For topics_handled, include only the topics actually discussed "
            "(any of: weather, jokes, time, math, chat). "
            "Set outcome to one of: completed, abandoned, transferred."
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
