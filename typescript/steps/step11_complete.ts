// Step 11: Complete Agent (TypeScript sibling, reference-only)
// Matches python/steps/step11_complete.py.
//
// The final polished version combining all four capabilities with
// clean organization using configure*() and register*() methods.
//
// Capabilities:
//   1. Dad jokes     - custom function (defineTool, runs on your server)
//   2. Weather       - DataMap (serverless, runs on SignalWire)
//   3. Date/time     - built-in skill (one line)
//   4. Math          - built-in skill (one line)

import * as fs from "node:fs";
import * as path from "node:path";
import { AgentBase, DataMap, FunctionResult } from "@signalwire/agents";

export class CompleteAgent extends AgentBase {
  constructor(route = "/") {
    super({ name: "complete-agent", route });

    this.configureVoice();
    this.configureParams();
    this.configurePrompts();
    this.registerJokeFunction();
    this.registerWeatherDatamap();
    this.registerSkills();
    this.configurePostPrompt();
  }

  // -- Voice and speech -----------------------------------------------------

  private configureVoice(): void {
    this.addLanguage({
      name: "English",
      code: "en-US",
      voice: "rime.spore",
      speechFillers: ["Um", "Well", "So"],
      functionFillers: [
        "Let me check on that for you...",
        "One moment while I look that up...",
        "Hang on just a sec...",
      ],
    });
    this.addHints([
      "Buddy",
      "weather",
      "joke",
      "temperature",
      "forecast",
      "Fahrenheit",
      "Celsius",
    ]);
  }

  // -- AI parameters --------------------------------------------------------

  private configureParams(): void {
    this.setParams({
      end_of_speech_timeout: 600,
      attention_timeout: 15000,
      attention_timeout_prompt:
        "Are you still there? I can help with weather, " +
        "jokes, math, or just chat!",
    });
  }

  // -- Prompts --------------------------------------------------------------

  private configurePrompts(): void {
    this.promptAddSection(
      "Personality",
      "You are Buddy, a cheerful and witty AI phone assistant. " +
        "You have a warm, upbeat personality and you genuinely enjoy " +
        "helping people. You're a bit of a dad joke enthusiast. " +
        "Think of yourself as that friendly neighbor who always " +
        "has a joke ready and knows what the weather is like."
    );
    this.promptAddSection("Voice Style", {
      body: "Since this is a phone conversation:",
      bullets: [
        "Keep responses to 1-2 sentences when possible",
        "Use conversational language, not formal or robotic",
        "React naturally to what the caller says",
        "Use smooth transitions between topics",
      ],
    });
    this.promptAddSection("Capabilities", {
      body: "You can help with:",
      bullets: [
        "Weather: current conditions for any city worldwide",
        "Jokes: endless supply of fresh dad jokes",
        "Date and time: current time in any timezone",
        "Math: calculations, percentages, unit conversions",
        "General chat: friendly conversation on any topic",
      ],
    });
    this.promptAddSection(
      "Greeting",
      "When the call starts, introduce yourself as Buddy and " +
        "briefly mention what you can help with. Keep the greeting " +
        "to one or two sentences -- don't list every capability."
    );
  }

  // -- Dad jokes (custom function, runs on our server) ----------------------

  private registerJokeFunction(): void {
    this.defineTool({
      name: "tell_joke",
      description:
        "Tell the caller a funny dad joke. Use this whenever " +
        "someone asks for a joke, humor, or to be entertained.",
      parameters: { type: "object", properties: {} },
      handler: (args, rawData) => this.onTellJoke(args, rawData),
      fillers: {
        "en-US": [
          "Let me think of a good one...",
          "Oh, I've got one for you...",
          "Here comes a good one...",
        ],
      },
    });
  }

  // WHY: removes the API Ninjas key dependency so attendees skip a prereq.
  private async onTellJoke(
    _args: Record<string, unknown>,
    _rawData: unknown
  ): Promise<FunctionResult> {
    try {
      const resp = await fetch("https://icanhazdadjoke.com/", {
        headers: {
          Accept: "application/json",
          "User-Agent": "signalwire-agents-sdk-workshop",
        },
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = (await resp.json()) as { joke?: string };
      if (!data.joke) {
        return new FunctionResult("I couldn't find a joke this time. Try again!");
      }
      return new FunctionResult(`Here's a dad joke: ${data.joke}`);
    } catch {
      return new FunctionResult(
        "My joke service is taking a break. Try again in a moment!"
      );
    }
  }

  // -- Weather (DataMap, runs on SignalWire) ---------------------------------

  private registerWeatherDatamap(): void {
    // WHY one webhook: DataMap runs multiple webhooks as sequential FALLBACKS,
    // not a pipeline -- there's no way to feed one webhook's response into the
    // next webhook's request. So we use wttr.in, which takes the city name
    // directly (no separate geocoding hop) and needs no API key, keeping the
    // workshop prerequisite-free.
    const weatherDm = new DataMap("get_weather")
      .description(
        "Get the current weather for a city. Use this when the caller asks " +
          "about weather, temperature, or conditions."
      )
      .parameter("city", "string", "The city to get weather for", {
        required: true,
      })
      .webhook("GET", "https://wttr.in/${enc:args.city}?format=j1")
      .output(
        new FunctionResult(
          "Weather in ${args.city}: " +
            "${response.current_condition[0].weatherDesc[0].value}, " +
            "${response.current_condition[0].temp_F} degrees Fahrenheit, " +
            "humidity ${response.current_condition[0].humidity} percent. " +
            "Feels like ${response.current_condition[0].FeelsLikeF} degrees."
        )
      )
      .fallbackOutput(
        new FunctionResult(
          "Sorry, I couldn't get the weather for ${args.city}. " +
            "Please check the city name and try again."
        )
      );

    this.registerSwaigFunction(weatherDm.toSwaigFunction());
  }

  // -- Built-in skills ------------------------------------------------------

  private registerSkills(): void {
    this.addSkill("datetime", { default_timezone: "America/New_York" });
    this.addSkill("math");
  }

  // -- Post-prompt (call summaries) -----------------------------------------

  private configurePostPrompt(): void {
    this.setPostPrompt(
      "Summarize this conversation in 2-3 sentences. " +
        "Note what the caller asked about (weather, jokes, time, math, etc.) " +
        "and how the interaction went."
    );
  }

  // Save call data to calls/ for debugging.
  // Upload JSON files to https://postpromptviewer.signalwire.io/
  onSummary(summary: unknown, rawData: unknown): void {
    fs.mkdirSync("calls", { recursive: true });
    const data = rawData as Record<string, unknown> | null | undefined;
    const callId =
      (data?.["call_id"] as string | undefined) ??
      new Date().toISOString().replace(/[:.]/g, "_");
    const filepath = path.join("calls", `${callId}.json`);
    fs.writeFileSync(filepath, JSON.stringify(rawData, null, 2));
    console.log(`Call summary saved: ${filepath}`);
  }
}
