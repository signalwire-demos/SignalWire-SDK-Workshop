"""
Step 11: Complete Agent
-----------------------
The final polished version combining all four capabilities with
clean organization using _configure_*() and _register_*() methods.

The prompt is a contexts/steps state machine in the shape the SignalWire
docs and blessed demos recommend: a handful of MEANINGFUL steps (one per
topic), each scoping exactly the tool it needs, with direct topic-to-topic
navigation so the caller is never railroaded through a menu.

Capabilities:
  1. Dad jokes     - custom function (define_tool, runs on your server)
  2. Weather       - server-side SWAIG tool (Open-Meteo, keyless)
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
        self._configure_live_events()
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
            "time", "date", "math", "calculate",
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

    # -- Debug event streaming (Live Wire) ----------------------------------

    def _configure_live_events(self):
        # The platform POSTs real-time per-turn debug events to this agent's
        # /debug_events endpoint during the call; we forward them to the Live
        # Wire bus so the browser-call panel can stream them over SSE.
        self.enable_debug_events(1)
        self.on_debug_event(self._on_debug_event)

    def _on_debug_event(self, event_type, data, *args, **kwargs):
        # Defensive: never raise into the SDK's request path.
        try:
            import live_events
            live_events.BUS.emit("ai", event_type, data if isinstance(data, dict) else {})
        except Exception as e:
            print(f"[live_events] dropped debug event: {e}", flush=True)

    # -- Prompt as a contexts/steps state machine ---------------------------
    # WHY: a state machine makes the platform emit `step_change` events into
    # call_log, which powers the State Flow tree (observability) and is the
    # live demonstration of System-Directed AI: each topic step exposes only
    # its own tool. Step granularity follows the blessed demos (one step per
    # phase, like holyguacamole's 5-step order flow): ask + tool call +
    # delivery happen inside one topic step, and every topic connects
    # directly to every other topic, so the caller is never bounced through
    # a menu hub.

    def _configure_contexts(self):
        contexts = self.define_contexts()
        ctx = contexts.add_context("default")

        # Global persona — applies across every step.
        ctx.add_section("Personality",
            "You are Buddy, a cheerful, witty AI phone assistant who loves dad "
            "jokes. You're showing the caller what a SignalWire agent can do.")
        ctx.add_section("Voice Style",
            "Phone conversation: 1-2 sentences per turn, warm and natural. "
            "React to the caller like a person would; never read out lists.")
        ctx.add_section("Physical Description",
            "Over video you appear as a friendly glowing robot; play along warmly if "
            "asked about your appearance.")
        ctx.add_section("Conversation Guide",
            "Follow the caller's lead; never force an order of topics. If they "
            "ask for something you can do, go straight to it. After finishing "
            "a topic, briefly offer one thing they haven't tried yet. Happily "
            "repeat a topic if asked. When the caller is done, or has tried "
            "everything, move to the wrap-up.")

        topics = ("weather", "joke", "time", "math")

        def reachable_from(name):
            # every OTHER topic plus the wrap-up
            return [t for t in topics if t != name] + ["wrap_up"]

        ctx.add_step("greeting",
            task=("Welcome the caller warmly, mention this demo call is "
                  "recorded for the workshop, and ask their first name."),
            bullets=[
                "Greet them by name once they share it (declining is fine).",
                "Offer what you can do in one natural sentence: live weather "
                "for any city, a dad joke, the current date and time, or a "
                "quick calculation.",
                "Go straight to whichever topic the caller picks.",
            ],
            criteria="The caller has been welcomed and picked a first topic "
                     "(or asked to wrap up).",
            functions="none",
            valid_steps=list(topics) + ["wrap_up"])

        ctx.add_step("weather",
            task="Get the caller live weather using get_weather.",
            bullets=[
                "If the caller already named a city, call get_weather right "
                "away; don't ask again.",
                "Otherwise ask which city they'd like.",
                "Share the result warmly in one sentence, then offer a topic "
                "they haven't tried yet.",
            ],
            criteria="The caller has heard the weather for their city.",
            functions=["get_weather"],
            valid_steps=reachable_from("weather"))

        ctx.add_step("joke",
            task="Tell the caller a dad joke using tell_joke.",
            bullets=[
                "Call tell_joke, deliver the joke with flair, and react "
                "playfully to your own punchline.",
                "If they want another, call tell_joke again.",
                "Then offer a topic they haven't tried yet.",
            ],
            criteria="The caller has heard a joke and your reaction to it.",
            functions=["tell_joke"],
            valid_steps=reachable_from("joke"))

        ctx.add_step("time",
            task="Share the current date and/or time.",
            bullets=[
                "Use get_current_time and get_current_date as needed; if the "
                "caller asked for a specific timezone, honor it.",
                "Share it conversationally, then offer a topic they haven't "
                "tried yet.",
            ],
            criteria="The caller has heard the date or time they asked about.",
            functions=["get_current_time", "get_current_date"],
            valid_steps=reachable_from("time"))

        ctx.add_step("math",
            task="Solve the caller's calculation using calculate.",
            bullets=[
                "If they haven't given one yet, ask what they'd like computed.",
                "Call calculate, share the answer plainly, then offer a topic "
                "they haven't tried yet.",
            ],
            criteria="The caller has heard the answer to their calculation.",
            functions=["calculate"],
            valid_steps=reachable_from("math"))

        ctx.add_step("wrap_up",
            task=("Recap whichever topics you actually covered together, "
                  "thank the caller, invite them to call back anytime, and "
                  "say goodbye."),
            criteria="The caller has been thanked and the call is ending.",
            functions="none",
            valid_steps=[])

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
                headers={"Accept": "application/json", "User-Agent": "signalwire-agents-sdk-workshop"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            joke = data.get("joke")
            if not joke:
                import live_events
                live_events.BUS.emit("swaig", "tell_joke", {"result": "no joke returned"})
                return FunctionResult("I couldn't find a joke this time. Try again!")
            import live_events
            live_events.BUS.emit("swaig", "tell_joke", {"result": joke[:80]})
            return FunctionResult(f"Here's a dad joke: {joke}")
        except requests.RequestException as e:
            import live_events
            live_events.BUS.emit("swaig", "tell_joke", {"error": str(e)[:80]})
            return FunctionResult("My joke service is taking a break. Try again in a moment!")

    # -- Weather (server-side SWAIG tool, runs on our server) ----------------

    def _register_weather(self):
        # Server-side define_tool, NOT a serverless DataMap: a real workshop call
        # proved SignalWire's DataMap engine left every ${...} empty for this
        # function. Fetching + formatting here is deterministic. See _weather.py.
        # No advance_to_step: the weather step delivers the result in-step, so
        # no forced transition is needed.
        from python.steps._weather import register_weather_tool
        register_weather_tool(self, live_emit=True)

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
