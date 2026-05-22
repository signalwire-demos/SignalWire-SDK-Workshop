// Step 8: Weather DataMap + Jokes (TypeScript sibling, reference-only)
// Matches python/steps/step08_weather.py.
//
// New concepts:
//   - DataMap: declare an API call, SignalWire executes it
//   - .parameter(): tell the AI what to extract from conversation
//   - .webhook(): the HTTP request SignalWire will make
//   - .output() / .fallbackOutput(): response templates with ${} variables
//   - Key difference: defineTool runs on YOUR server, DataMap runs on SIGNALWIRE

import * as fs from "node:fs";
import * as path from "node:path";
import { AgentBase, DataMap, FunctionResult } from "@signalwire/agents";

export class WeatherJokeAgent extends AgentBase {
  constructor(route = "/") {
    super({ name: "weather-joke-agent", route });

    this.addLanguage({
      name: "English",
      code: "en-US",
      voice: "rime.spore",
      speechFillers: ["Um", "Well"],
      functionFillers: ["Let me check on that...", "One moment..."],
    });

    this.promptAddSection(
      "Role",
      "You are a friendly assistant named Buddy. " +
        "You help people with weather information and tell great jokes. " +
        "Keep your responses short since this is a phone call."
    );

    this.promptAddSection("Guidelines", {
      body: "Follow these guidelines:",
      bullets: [
        "When someone asks about weather, use the get_weather function",
        "When someone asks for a joke, use the tell_joke function",
        "Be warm, friendly, and conversational",
      ],
    });

    this.registerJokeFunction();
    this.registerWeatherDatamap();

    this.setPostPrompt(
      "Summarize this conversation in 2-3 sentences. " +
        "Note what the caller asked about (weather, jokes, etc.) " +
        "and how the interaction went."
    );
  }

  // -- Dad jokes (runs on our server) ---------------------------------------

  private registerJokeFunction(): void {
    this.defineTool({
      name: "tell_joke",
      description:
        "Tell the caller a funny dad joke. Use this whenever " +
        "someone asks for a joke or humor.",
      parameters: { type: "object", properties: {} },
      handler: (args, rawData) => this.onTellJoke(args, rawData),
      fillers: { "en-US": ["Let me think of a good one..."] },
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
          "User-Agent": "chicago-roadshow-2026",
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

  // -- Weather (runs on SignalWire via DataMap) ------------------------------

  private registerWeatherDatamap(): void {
    // WHY two hops: Open-Meteo splits geocoding from forecast. First call
    // turns the city name into lat/lon; second call fetches current weather.
    const weatherDm = new DataMap("get_weather")
      .description(
        "Get the current weather for a city. Use this when the caller asks " +
          "about weather, temperature, or conditions."
      )
      .parameter("city", "string", "The city to get weather for", {
        required: true,
      })
      .webhook(
        "GET",
        "https://geocoding-api.open-meteo.com/v1/search" +
          "?name=${enc:args.city}&count=1&format=json"
      )
      .webhook(
        "GET",
        "https://api.open-meteo.com/v1/forecast" +
          "?latitude=${response.results[0].latitude}" +
          "&longitude=${response.results[0].longitude}" +
          "&current=temperature_2m,relative_humidity_2m,apparent_temperature" +
          "&temperature_unit=fahrenheit"
      )
      .output(
        new FunctionResult(
          "Weather in ${args.city}: " +
            "${response.current.temperature_2m} degrees Fahrenheit, " +
            "humidity ${response.current.relative_humidity_2m} percent. " +
            "Feels like ${response.current.apparent_temperature} degrees."
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
