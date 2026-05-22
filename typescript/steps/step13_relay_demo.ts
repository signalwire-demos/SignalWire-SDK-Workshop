// Step 13: RELAY pillar - WebSocket client demo (TypeScript sibling, reference-only)
// Matches python/steps/step13_relay_demo.py.
//
// Runs as a standalone script. Demonstrates:
//   1. Connect via the Relay client
//   2. Subscribe to incoming-call events
//   3. Stream live transcripts to stdout
//   4. Optionally place one outbound call (gated on OUTBOUND_TO)

import { Client } from "@signalwire/relay";

async function main(): Promise<number> {
  const project = process.env["SIGNALWIRE_PROJECT_ID"];
  const token = process.env["SIGNALWIRE_TOKEN"];

  if (!project || !token) {
    const missing = ["SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN"].filter(
      (k) => !process.env[k]
    );
    console.error(`[error] missing required env var: ${missing[0]}`);
    return 2;
  }

  const relayFrom = process.env["RELAY_FROM"];
  const outboundTo = process.env["OUTBOUND_TO"];

  const client = new Client({ project, token });
  await client.connect();
  console.log("[connected] relay client online");

  client.calling.on("call.received", async (call) => {
    console.log(`[incoming] ${call.fromNumber} -> ${call.toNumber}`);
    await call.answer();

    // WHY per-call registration: each call is its own event source.
    // A client-wide handler would not know which call a transcript belongs to.
    call.on("transcription", (t: unknown) => {
      const transcript = t as { speaker?: string; text?: string };
      const speaker = transcript.speaker ?? "?";
      const text = transcript.text ?? "";
      console.log(`[transcript] (${speaker}) ${text}`);
    });
  });

  // WHY env-gated: prevents surprise outbound dials during workshop demos
  // where attendees might run this without realizing.
  if (outboundTo && relayFrom) {
    console.log(`[outbound] dialing ${outboundTo} from ${relayFrom}`);
    const call = await client.calling.dial({ from_: relayFrom, to: outboundTo });
    console.log(`[outbound] id=${call.id} state=${call.state}`);
  } else if (outboundTo && !relayFrom) {
    console.log("[warn] OUTBOUND_TO set but RELAY_FROM missing; skipping outbound");
  }

  console.log("[listening] for events. SIGTERM to stop.");
  await client.run();
  return 0;
}

main().then((code) => process.exit(code)).catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
