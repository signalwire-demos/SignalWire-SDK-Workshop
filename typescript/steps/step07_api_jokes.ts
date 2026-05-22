// Step 7: Live API Jokes (TypeScript sibling, reference-only)
// Matches python/steps/step07_api_jokes.py.
//
// New concepts:
//   - Calling external APIs from a SWAIG function handler
//   - Graceful error handling when APIs fail

import * as fs from "node:fs";
import * as path from "node:path";
import { AgentBase, FunctionResult } from "@signalwire/agents";

export class JokeAgent extends AgentBase {
  constructor(route = "/") {
    super({ name: "joke-agent-api", route });

    this.addLanguage({
      name: "English",
      code: "en-US",
      voice: "rime.spore",
      speechFillers: ["Um", "Well"],
      functionFillers: ["Let me think of a good one..."],
    });

    this.promptAddSection(
      "Role",
      "You are a friendly assistant named Buddy. " +
        "You love telling jokes and making people laugh. " +
        "Keep your responses short since this is a phone call."
    );

    this.promptAddSection("Guidelines", {
      body: "Follow these guidelines:",
      bullets: [
        "When someone asks for a joke, use the tell_joke function",
        "After telling a joke, pause for a reaction before offering another",
        "Be enthusiastic and have fun with it",
      ],
    });

    this.defineTool({
      name: "tell_joke",
      description:
        "Tell the caller a funny dad joke. Use this whenever " +
        "someone asks for a joke, humor, or to be entertained.",
      parameters: { type: "object", properties: {} },
      handler: (args, rawData) => this.onTellJoke(args, rawData),
    });

    this.setPostPrompt(
      "Summarize this conversation in 2-3 sentences. " +
        "Note which jokes were told and how the caller reacted."
    );
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
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
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
