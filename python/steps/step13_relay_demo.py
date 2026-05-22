"""
Step 13: RELAY pillar - WebSocket client demo
---------------------------------------------
Runs as a standalone script. The landing page kicks it off via
POST /run/relay and streams stdout back via SSE.

Capabilities:
  1. Connect via the Relay client
  2. Subscribe to incoming-call events
  3. Stream live transcripts to stdout
  4. Optionally place one outbound call (gated on OUTBOUND_TO)
"""

import asyncio
import os
import sys
from signalwire.relay import Client


async def main() -> int:
    try:
        project = os.environ["SIGNALWIRE_PROJECT_ID"]
        token = os.environ["SIGNALWIRE_TOKEN"]
    except KeyError as missing:
        print(f"[error] missing required env var: {missing.args[0]}", file=sys.stderr)
        return 2

    relay_from = os.environ.get("RELAY_FROM")
    outbound_to = os.environ.get("OUTBOUND_TO")

    client = Client(project=project, token=token)
    await client.connect()
    print("[connected] relay client online")

    @client.calling.on("call.received")
    async def handle_incoming(call):
        print(f"[incoming] {call.from_number} -> {call.to_number}")
        await call.answer()

        # WHY per-call registration: each call is its own event source.
        # A client-wide handler would not know which call a transcript belongs to.
        @call.on("transcription")
        def on_transcript(t):
            speaker = getattr(t, "speaker", "?")
            text = getattr(t, "text", "")
            print(f"[transcript] ({speaker}) {text}")

    # WHY env-gated: prevents surprise outbound dials during workshop demos
    # where attendees might run this without realizing.
    if outbound_to and relay_from:
        print(f"[outbound] dialing {outbound_to} from {relay_from}")
        call = await client.calling.dial(from_=relay_from, to=outbound_to)
        print(f"[outbound] id={call.id} state={call.state}")
    elif outbound_to and not relay_from:
        print("[warn] OUTBOUND_TO set but RELAY_FROM missing; skipping outbound")

    print("[listening] for events. SIGTERM to stop.")
    await client.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(130)
