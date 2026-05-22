# Chicago Roadshow 2026 - SignalWire Workshop (AI Agent + REST + RELAY)

> **Duration:** ~75 minutes | **Level:** Beginner | **No Docker, ngrok, or local setup required**
>
> By the end of this workshop, you'll have a live AI assistant on a real phone number that tells jokes, reports weather, knows the time, and does math -- all built by you from scratch. You'll also explore the AI Agent + REST + RELAY pillars of the SignalWire platform.

## What You'll Learn

Three different ways to add capabilities to an AI agent:

1. **Custom functions** -- you write the handler, full control
2. **DataMap** -- declare an API call, SignalWire runs it serverlessly
3. **Skills** -- one line of code, instant capability

---

## Three Pillars

SignalWire is a programmable communications platform. This workshop teaches three of its pillars:

- **AI Agent** (steps 4-11): build a live AI phone agent using `signalwire-agents`. Includes custom SWAIG functions, serverless DataMap calls, and built-in skills. The caller dials a real phone number; SignalWire routes the call to your Replit-hosted agent.
- **REST** (step 12): use the SignalWire REST client to list phone numbers on your project, send SMS, fetch recent call history, and programmatically point a phone number's voice handler at the agent URL.
- **RELAY** (step 13): connect over WebSocket via the Relay client. Subscribe to live incoming-call events, stream transcripts to stdout, and optionally place outbound calls programmatically.

Steps 4-11 are phone-call driven (you dial your workshop number). Steps 12 and 13 are Run-button driven on the landing page (the demo executes server-side and streams logs back to your browser).

---

## Prerequisites

You'll need accounts for these services (all have free tiers):

| Service | What it's for | Sign up |
|---------|--------------|---------|
| **SignalWire** | AI voice platform + phone number (required for steps 12-13; optional for 4-11) | [signalwire.com](https://signalwire.com) |

### SignalWire Setup

1. Create a SignalWire account and note your **Space Name** (from the URL: `https://YOUR-SPACE.signalwire.com`)
2. Go to **API** in the sidebar -- copy your **Project ID** and create an **API Token**
3. Go to **Phone Numbers** > **Buy a Number** -- pick any number (trial credits cover it)

---

## Quick Start

### 1. Add Secrets (Optional)

Open the **Secrets** tab (lock icon in the Replit sidebar) and add API keys for the steps that need them:

| Secret | Value |
|--------|-------|
| `SIGNALWIRE_PROJECT_ID` | Required for steps 12-13. From SignalWire Dashboard -> API. |
| `SIGNALWIRE_TOKEN` | Required for steps 12-13. Create one in SignalWire Dashboard -> API. |
| `SIGNALWIRE_SPACE` | Required for steps 12-13. Your space hostname, e.g. your-space.signalwire.com. |
| `SWML_BASIC_AUTH_USER` | Optional | Override auth username (default: `workshop`) |
| `SWML_BASIC_AUTH_PASSWORD` | Optional | Override auth password (default: `password`) |

No SignalWire credentials are needed for steps 4-11 -- those steps only serve SWML documents that SignalWire fetches.

### 2. Click Run

All workshop agents start simultaneously. A **landing page** opens with every step, its SWML URL, and setup instructions.

### 3. Connect Your Phone Number

1. Go to your [SignalWire Dashboard](https://signalwire.com) > **Phone Numbers**
2. Click your number > **Edit Settings**
3. Click **Select Resource** > **+ add**
4. Create a new **Script** -- choose **SWML Script**
5. Under **Handle Calls Using**, select **External URL**
6. Paste any SWML URL from the console output
7. **Save** -- then call the number!

> Don't forget the **trailing slash** on the URL.

To try a different step, just change which URL your phone number points to in the dashboard. No restart needed -- all agents are always running.

---

## How This Workshop Works

When you click **Run**, a single server starts with every workshop step on its own route:

| Route | Agent | Capabilities |
|-------|-------|-------------|
| `/step04` | Hello Agent | Basic chat |
| `/step06` | Hardcoded Jokes | Chat + jokes from a list |
| `/step07` | Live API Jokes | Chat + fresh jokes from icanhazdadjoke |
| `/step08` | Weather + Jokes | Jokes + weather via DataMap |
| `/step09` | Polished Agent | Same as 08, better personality |
| `/step10` | Agent with Skills | Weather + jokes + date/time + math |
| `/step11` | Complete Agent | Everything, production-ready organization |
| `/run/rest` (*) | REST pillar demo | Run from landing page, not by phone call |
| `/run/relay` (*) | RELAY pillar demo | Run from landing page, not by phone call |

\* Steps 12 and 13 are Run-button driven on the landing page; they do not handle inbound phone calls directly.

The code for each agent lives in `python/steps/`. Read through each file to see what changes between steps -- that's the learning path.

---

## Source Views

Every step card on the landing page has two buttons:

- **View Python Source** -- links to the runtime file in `python/steps/`
- **View TypeScript Source** -- links to the reference-only sibling in `typescript/steps/`

The TypeScript files are not executed at workshop runtime. They exist so attendees can compare the same agent or script in two languages. Workshop runtime is Python only.

---

## Step 4: Hello Agent

> **Code:** `python/steps/step04_hello.py` | **Route:** `/step04`

The simplest possible agent. Point your phone at the `/step04` URL and call -- Buddy greets you and chats.

```python
from signalwire import AgentBase
```

`AgentBase` is the foundation class for every agent.

```python
self.add_language("English", "en-US", "rime.spore", speech_fillers=["Um", "Well"])
```

Sets up English speech recognition and `rime.spore`, a warm, friendly TTS voice. `speech_fillers` are little sounds the agent makes while "thinking."

```python
self.prompt_add_section("Role", "You are a friendly assistant named Buddy...")
```

The AI's personality and instructions. This text shapes everything about how the agent behaves.

```python
self.set_post_prompt("Summarize this conversation...")
```

After each call ends, the AI generates a summary. `on_summary()` saves it to `calls/` as JSON. Upload these to [postpromptviewer.signalwire.io](https://postpromptviewer.signalwire.io/) to visualize conversations.

> **Try it:** Point your phone at `/step04`, call, and chat. The agent can talk but can't *do* anything yet.

---

## Step 6: Your First SWAIG Function -- Hardcoded Jokes

> **Code:** `python/steps/step06_hardcoded_jokes.py` | **Route:** `/step06`

Teaches the AI to tell jokes using a SWAIG (SignalWire AI Gateway) function.

```python
from signalwire import AgentBase, FunctionResult
```

`FunctionResult` is how you return data from a function. The AI takes this text and weaves it into its spoken response.

```python
self.define_tool(
    name="tell_joke",
    description="Tell the caller a funny joke. Use this whenever someone asks for a joke.",
    parameters={"type": "object", "properties": {}},
    handler=self.on_tell_joke,
)
```

- **`description`** -- critical: tells the AI *when* to call this function
- **`parameters`** -- what the AI should extract from conversation (empty here -- jokes need no input)
- **`handler`** -- your code that runs when the AI calls this function

```python
def on_tell_joke(self, args, raw_data):
    joke = random.choice(JOKES)
    return FunctionResult(f"Here's a joke: {joke}")
```

> **Try it:** Point your phone at `/step06` and say "tell me a joke."

---

## Step 7: Calling a Live API

> **Code:** `python/steps/step07_api_jokes.py` | **Route:** `/step07`

Replaces hardcoded jokes with fresh ones from icanhazdadjoke.com. No API key required.

The handler now calls an external API:

```python
def on_tell_joke(self, args, raw_data):
    resp = requests.get(
        "https://icanhazdadjoke.com/",
        headers={"Accept": "application/json", "User-Agent": "chicago-roadshow-2026"},
        timeout=5,
    )
    joke = resp.json().get("joke", "Why did the chicken cross the road? To get to the other side!")
    return FunctionResult(f"Here's a dad joke: {joke}")
```

Error handling ensures the agent says something graceful if the API is down.

> **Try it:** Point your phone at `/step07` and ask for multiple jokes -- each one is different.

---

## Step 8: DataMap -- The Serverless Approach

> **Code:** `python/steps/step08_weather.py` | **Route:** `/step08`

Adds weather lookups using **DataMap** -- you declare an API call and SignalWire executes it on their infrastructure. Your server never handles the request. This step uses Open-Meteo, which requires no API key.

The DataMap makes **two** webhook calls: first a geocode lookup to resolve the city name to coordinates, then a forecast call to get current conditions.

Think of it this way:

- **define_tool** = "Send the request to my server, I'll call the API"
- **DataMap** = "Here's the API URL and response format -- you call it, SignalWire"

```python
from signalwire.core.data_map import DataMap

weather_dm = (
    DataMap("get_weather")
    .description("Get the current weather for a city...")
    .parameter("city", "string", "The city to get weather for", required=True)
    .webhook("GET", "https://geocoding-api.open-meteo.com/v1/search?name=${enc:args.city}&count=1")
    .webhook("GET", "https://api.open-meteo.com/v1/forecast?latitude=${response.results[0].latitude}&longitude=${response.results[0].longitude}&current_weather=true")
    .output(FunctionResult("Weather in ${args.city}: ${response.current_weather.weathercode}..."))
    .fallback_output(FunctionResult("Sorry, couldn't get weather for ${args.city}."))
)
self.register_swaig_function(weather_dm.to_swaig_function())
```

- **`${enc:args.city}`** -- the city parameter, URL-encoded, substituted at call time
- **`${response.current_weather.temperature}`** -- pulled from the API's JSON response
- No API key needed -- Open-Meteo is free and open

> **Try it:** Point your phone at `/step08` and ask "What's the weather in Tokyo?" Then ask for a joke -- both work.

---

## Step 9: Polish and Personality

> **Code:** `python/steps/step09_polish.py` | **Route:** `/step09`

Same capabilities as Step 8, much better conversation experience.

```python
self.set_params({
    "end_of_speech_timeout": 600,     # 600ms pause before responding
    "attention_timeout": 15000,        # Re-engage after 15s silence
    "attention_timeout_prompt": "Are you still there?...",
})

self.add_hints(["Buddy", "weather", "joke", "temperature"])
```

- **`end_of_speech_timeout`** -- the agent waits a natural beat instead of jumping in immediately
- **`attention_timeout`** -- re-engages if the caller goes quiet
- **`add_hints()`** -- helps speech recognition ("Buddy" could sound like "body" without a hint)
- **Richer prompts** -- personality, voice style, and capabilities sections
- **More fillers** -- variety so the agent doesn't repeat itself

> **Try it:** Compare `/step09` to `/step08` -- same features, noticeably smoother conversation.

---

## Step 10: Skills -- The Easy Way

> **Code:** `python/steps/step10_skills.py` | **Route:** `/step10`

Adds date/time and math with two lines of code:

```python
self.add_skill("datetime", {"default_timezone": "America/New_York"})
self.add_skill("math")
```

Skills are pre-built capabilities that ship with the SDK. No handler, no API, no DataMap.

### Compare the Three Approaches

| Capability | Approach | Lines of Code | Your Server Handles It? |
|-----------|----------|---------------|------------------------|
| Dad Jokes | `define_tool` | ~30 lines | Yes |
| Weather | DataMap | ~15 lines | No (SignalWire) |
| DateTime | Skill | 1 line | No (built-in) |
| Math | Skill | 1 line | No (built-in) |

**When to use which:**
- **Skills** -- when one exists for what you need. Fastest path, zero maintenance.
- **DataMap** -- when you need to call a REST API. No server code needed.
- **define_tool** -- when you need custom logic, database access, or complex processing.

> **Try it:** Point your phone at `/step10` and try "What time is it in Tokyo?" and "What's 15% tip on $47.50?"

---

## Step 11: The Finished Agent

> **Code:** `python/steps/step11_complete.py` | **Route:** `/step11`

Everything polished and organized into clean private methods:

```python
class CompleteAgent(AgentBase):
    def __init__(self):
        super().__init__(name="complete-agent")
        self._configure_voice()
        self._configure_params()
        self._configure_prompts()
        self._register_joke_function()
        self._register_weather_datamap()
        self._register_skills()
        self._configure_post_prompt()
```

This `_configure_*` / `_register_*` pattern is the standard way to organize larger agents in the SDK.

> **Try it:** Point your phone at `/step11` and run through all capabilities:
> 1. "Hey, what time is it?" -- datetime skill
> 2. "What's the weather in Paris?" -- DataMap weather
> 3. "Tell me a joke!" -- icanhazdadjoke dad jokes
> 4. "What's 18% tip on $86?" -- math skill

---

## Step 12: REST pillar - RestClient

> **Code:** `python/steps/step12_rest_demo.py` | **Run:** Landing page "Run REST Demo" button

The REST client lets you control phone numbers, messages, and calls from outside the agent. This step does four things:

1. Lists every phone number on the project (sanity check that `SMS_FROM` is real)
2. Sends an SMS from `SMS_FROM` to `SMS_TO`
3. Lists the last 10 calls
4. If `AGENT_VOICE_URL` is set, points `SMS_FROM`'s voice handler at it -- so attendees stop having to click around the dashboard to switch which step their number routes to

`AGENT_VOICE_URL` defaults to the Step 11 URL when unset.

> **Try it:** Click "Run REST Demo" on the landing page. If `SMS_FROM` / `SMS_TO` are not set in Secrets, the page will prompt you for them inline. The script's stdout streams back to the log pane below the button.

---

## Step 13: RELAY pillar - WebSocket client

> **Code:** `python/steps/step13_relay_demo.py` | **Run:** Landing page "Run RELAY Demo" button

The Relay client opens a persistent WebSocket to SignalWire and gets real-time events: incoming calls, transcripts, call state changes. This step:

1. Connects via the Relay client
2. Subscribes to incoming-call events and auto-answers each one
3. Streams the live transcript of each call to stdout
4. If `OUTBOUND_TO` is set, places one outbound call from `RELAY_FROM` to that number

The outbound dial is gated on env so you don't accidentally fire a call during a demo.

> **Try it:** Click "Run RELAY Demo" on the landing page. The script stays running and prints transcripts as calls happen. Click "Run RELAY Demo" again to restart it (the previous run is SIGTERM'd cleanly).

---

## Quick Reference

### Secrets

| Secret | Required? | Purpose |
|--------|-----------|---------|
| `SIGNALWIRE_PROJECT_ID` | Step 12-13 | Required for REST and RELAY pillars -- from SignalWire Dashboard -> API |
| `SIGNALWIRE_TOKEN` | Step 12-13 | Required for REST and RELAY pillars -- create in SignalWire Dashboard -> API |
| `SIGNALWIRE_SPACE` | Step 12-13 | Your space hostname, e.g. your-space.signalwire.com |
| `SWML_BASIC_AUTH_USER` | Optional | Override auth username (default: `workshop`) |
| `SWML_BASIC_AUTH_PASSWORD` | Optional | Override auth password (default: `password`) |

### Troubleshooting

| Problem | Fix |
|---------|-----|
| REST/RELAY steps fail | Add `SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`, `SIGNALWIRE_SPACE` in Secrets |
| No SWML URLs printed | Make sure you're on Replit, or set `SWML_PROXY_URL_BASE` locally |
| Call connects but no audio | Check that your SignalWire space and credentials are correct |
| `ModuleNotFoundError` | Click Run once -- Replit installs dependencies automatically |
| Agent doesn't call functions | Check the function `description` -- AI needs clear guidance |
| Speech recognition is wrong | Add `add_hints()` for commonly misheard words |

### Running Locally (Without Replit)

```bash
export SWML_PROXY_URL_BASE=https://your-public-url
export SIGNALWIRE_PROJECT_ID=your-project-id    # for steps 12-13
export SIGNALWIRE_TOKEN=your-api-token           # for steps 12-13
export SIGNALWIRE_SPACE=your-space.signalwire.com  # for steps 12-13
python main.py
```

### Key Concepts

**SWAIG Functions** -- tools the AI calls during a conversation. Caller says "tell me a joke" -> AI calls `tell_joke` -> your handler returns a `FunctionResult` -> AI speaks the result.

**DataMap** -- declare an API call and SignalWire executes it serverlessly. Your server never handles the request.

**Skills** -- pre-built capabilities. One function call, zero code to write.

```python
# Three ways to add capabilities:

# 1. Custom function (full control, runs on your server)
self.define_tool(name="...", description="...", parameters={...}, handler=self.my_handler)

# 2. DataMap (serverless, runs on SignalWire)
dm = DataMap("name").description("...").parameter(...).webhook(...).output(...)
self.register_swaig_function(dm.to_swaig_function())

# 3. Skill (pre-built, one line)
self.add_skill("skill_name", {config})
```

---

## What's Next

- **Contexts and workflows** -- guide conversations through structured steps
- **State management** -- track information across the call
- **Multi-agent servers** -- different agents on different routes (that's how this workshop works!)
- **DataSphere** -- connect agents to knowledge bases
- **Call transfer** -- hand off to humans or other agents

### Resources

- [SignalWire Documentation](https://docs.signalwire.com)
- [Post-Prompt Viewer](https://postpromptviewer.signalwire.io/) -- upload call JSON to debug conversations
- [Python SDK](https://github.com/signalwire/signalwire-python)
