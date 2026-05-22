// Step 4: Hello Agent (TypeScript sibling, reference-only)
// Matches python/steps/step04_hello.py. Runtime uses the Python file;
// this exists so workshop attendees can see the same agent expressed
// in @signalwire/agents.
//
// Concepts:
//   - AgentBase: the foundation class for every agent
//   - addLanguage(): speech recognition + TTS voice
//   - promptAddSection(): personality and instructions
//   - setPostPrompt() + onSummary(): save call data for debugging

import * as fs from "node:fs";
import * as path from "node:path";
import { AgentBase } from "@signalwire/agents";

export class HelloAgent extends AgentBase {
  constructor(route = "/") {
    super({ name: "hello-agent", route });

    // "rime.spore" is a warm, friendly TTS voice
    this.addLanguage({
      name: "English",
      code: "en-US",
      voice: "rime.spore",
      speechFillers: ["Um", "Well"],
    });

    // The AI's personality and instructions
    this.promptAddSection(
      "Role",
      "You are a friendly assistant named Buddy. " +
        "You greet callers warmly, ask how their day is going, " +
        "and have a brief pleasant conversation. " +
        "Keep your responses short since this is a phone call."
    );

    // After each call, the AI generates a summary
    this.setPostPrompt(
      "Summarize this conversation in 2-3 sentences. " +
        "Include what the caller wanted and how the conversation went."
    );
  }

  // Save post-prompt data to calls/ for debugging.
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
