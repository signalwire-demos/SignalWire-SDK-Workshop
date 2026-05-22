"""
Step 12: REST pillar - RestClient demo
--------------------------------------
Runs as a standalone script. The landing page kicks it off via
POST /run/rest and streams stdout back via SSE.

Capabilities:
  1. List phone numbers on the project
  2. Send an SMS
  3. List recent calls
  4. Point the workshop number's voice URL at the agent (step 11)
"""

import os
import sys
from signalwire.rest import Client as RestClient


def main() -> int:
    try:
        project = os.environ["SIGNALWIRE_PROJECT_ID"]
        token = os.environ["SIGNALWIRE_TOKEN"]
        space = os.environ["SIGNALWIRE_SPACE"]
        sms_from = os.environ["SMS_FROM"]
        sms_to = os.environ["SMS_TO"]
    except KeyError as missing:
        print(f"[error] missing required env var: {missing.args[0]}", file=sys.stderr)
        return 2

    agent_voice_url = os.environ.get("AGENT_VOICE_URL")

    client = RestClient(project, token, signalwire_space_url=space)

    print("--- Phone numbers on this project ---")
    # WHY list first: confirms SMS_FROM is owned by this project before
    # we try to send from it. Catches typos in the dashboard early.
    numbers = list(client.incoming_phone_numbers.list(limit=20))
    for num in numbers:
        print(num.phone_number, "|", num.friendly_name)

    print("\n--- Sending SMS ---")
    msg = client.messages.create(
        from_=sms_from,
        to=sms_to,
        body="Hello from the Chicago Roadshow 2026 REST demo.",
    )
    print("sid:", msg.sid, "| status:", msg.status)

    print("\n--- Recent calls (last 10) ---")
    for call in client.calls.list(limit=10):
        print(call.sid, call.from_, "->", call.to, "|", call.status, "|", call.start_time)

    if agent_voice_url:
        print("\n--- Pointing voice handler at agent URL ---")
        # WHY last: a misconfigured voice_url breaks the live agent route
        # mid-workshop. Do this only after every other call succeeded.
        target = next(
            (n for n in numbers if n.phone_number == sms_from),
            None,
        )
        if target is None:
            print(f"[warn] {sms_from} not found on project; skipping voice_url update")
        else:
            client.incoming_phone_numbers(target.sid).update(voice_url=agent_voice_url)
            print(f"Updated {target.phone_number} -> {agent_voice_url}")

    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
