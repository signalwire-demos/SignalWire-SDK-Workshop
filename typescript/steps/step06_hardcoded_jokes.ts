// Step 6: Hardcoded Jokes (TypeScript sibling, reference-only)
// Matches python/steps/step06_hardcoded_jokes.py.
//
// New concepts:
//   - FunctionResult: return data from a SWAIG function
//   - defineTool(): register a function the AI can call
//   - description: tells the AI *when* to use the function (critical!)
//   - parameters: what info the AI extracts from conversation
//   - functionFillers: phrases spoken while your function runs

import * as fs from "node:fs";
import * as path from "node:path";
import { AgentBase, FunctionResult } from "@signalwire/agents";

const JOKES: readonly string[] = [
  "Why do programmers prefer dark mode? Because light attracts bugs.",
  "I told my wife she was drawing her eyebrows too high. She looked surprised.",
  "What do you call a fake noodle? An impasta.",
  "Why don't scientists trust atoms? Because they make up everything.",
  "I'm reading a book about anti-gravity. It's impossible to put down.",
  "What did the ocean say to the beach? Nothing, it just waved.",
  "Why did the scarecrow win an award? He was outstanding in his field.",
  "I used to hate facial hair, but then it grew on me.",
];

export class JokeAgent extends AgentBase {
  constructor(route = "/") {
    super({ name: "joke-agent-hardcoded", route });

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

    // The AI decides when to call this based on the description
    this.defineTool({
      name: "tell_joke",
      description:
        "Tell the caller a funny joke. Use this whenever " +
        "someone asks for a joke or humor.",
      parameters: { type: "object", properties: {} },
      handler: (args, rawData) => this.onTellJoke(args, rawData),
    });

    this.setPostPrompt(
      "Summarize this conversation in 2-3 sentences. " +
        "Note which jokes were told and how the caller reacted."
    );
  }

  private onTellJoke(
    _args: Record<string, unknown>,
    _rawData: unknown
  ): FunctionResult {
    const joke = JOKES[Math.floor(Math.random() * JOKES.length)];
    return new FunctionResult(`Here's a joke: ${joke}`);
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
