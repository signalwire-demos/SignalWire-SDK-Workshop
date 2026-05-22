// Step 12: REST pillar - RestClient demo (TypeScript sibling, reference-only)
// Matches python/steps/step12_rest_demo.py.
//
// Runs as a standalone script. Demonstrates four REST capabilities:
//   1. List phone numbers on the project
//   2. Send an SMS
//   3. List recent calls
//   4. Point the workshop number's voice URL at the agent (step 11)

import { RestClient } from "@signalwire/node";

async function main(): Promise<number> {
  const project = process.env["SIGNALWIRE_PROJECT_ID"];
  const token = process.env["SIGNALWIRE_TOKEN"];
  const space = process.env["SIGNALWIRE_SPACE"];
  const smsFrom = process.env["SMS_FROM"];
  const smsTo = process.env["SMS_TO"];

  if (!project || !token || !space || !smsFrom || !smsTo) {
    const missing = ["SIGNALWIRE_PROJECT_ID", "SIGNALWIRE_TOKEN", "SIGNALWIRE_SPACE", "SMS_FROM", "SMS_TO"]
      .filter((k) => !process.env[k]);
    console.error(`[error] missing required env var: ${missing[0]}`);
    return 2;
  }

  const agentVoiceUrl = process.env["AGENT_VOICE_URL"];

  const client = new RestClient(project, token, { signalwireSpaceUrl: space });

  console.log("--- Phone numbers on this project ---");
  // WHY list first: confirms SMS_FROM is owned by this project before
  // we try to send from it. Catches typos in the dashboard early.
  const numbers = await client.incomingPhoneNumbers.list({ limit: 20 });
  for (const num of numbers) {
    console.log(num.phoneNumber, "|", num.friendlyName);
  }

  console.log("\n--- Sending SMS ---");
  const msg = await client.messages.create({
    from_: smsFrom,
    to: smsTo,
    body: "Hello from the Chicago Roadshow 2026 REST demo.",
  });
  console.log("sid:", msg.sid, "| status:", msg.status);

  console.log("\n--- Recent calls (last 10) ---");
  const calls = await client.calls.list({ limit: 10 });
  for (const call of calls) {
    console.log(call.sid, call.from_, "->", call.to, "|", call.status, "|", call.startTime);
  }

  if (agentVoiceUrl) {
    console.log("\n--- Pointing voice handler at agent URL ---");
    // WHY last: a misconfigured voiceUrl breaks the live agent route
    // mid-workshop. Do this only after every other call succeeded.
    const target = numbers.find((n) => n.phoneNumber === smsFrom);
    if (!target) {
      console.log(`[warn] ${smsFrom} not found on project; skipping voice_url update`);
    } else {
      await client.incomingPhoneNumbers(target.sid).update({ voiceUrl: agentVoiceUrl });
      console.log(`Updated ${target.phoneNumber} -> ${agentVoiceUrl}`);
    }
  }

  console.log("\n[done]");
  return 0;
}

main().then((code) => process.exit(code)).catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
