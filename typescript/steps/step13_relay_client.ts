// Step 13: RELAY pillar - in-browser click-to-call (TS sibling, reference-only).
// Mirrors web/relay-client.js. The runtime uses the plain-JS file; this typed
// version shows the same flow against the @signalwire/js browser SDK shape.

// The SDK is loaded from https://cdn.signalwire.com/@signalwire/js and exposes
// a global SignalWire. We declare the slice we use so this file type-checks
// without installing the package.
interface CallSession {
  on(event: "destroy", handler: () => void): void;
  start(): Promise<void>;
  hangup(): Promise<void>;
}
interface FabricClient {
  dial(params: {
    to: string;
    audio: boolean;
    video: boolean;
    rootElement?: HTMLElement | null;
  }): Promise<CallSession>;
}
declare const SignalWire: {
  SignalWire(params: { token: string }): Promise<FabricClient>;
  WebRTC: { requestPermissions(c: { audio: boolean; video: boolean }): Promise<void> };
};

interface CallRefs {
  rootEl: HTMLElement | null;
  statusEl: HTMLElement | null;
}

let client: FabricClient | null = null;
let call: CallSession | null = null;

export async function startCall(refs: CallRefs): Promise<void> {
  const setStatus = (t: string) => {
    if (refs.statusEl) refs.statusEl.textContent = t;
  };
  try {
    // WHY permissions first: browsers block media capture until granted.
    setStatus("Requesting microphone...");
    await SignalWire.WebRTC.requestPermissions({ audio: true, video: false });

    // WHY fresh token per call: subscriber tokens are short-lived JWTs.
    setStatus("Getting a token...");
    const resp = await fetch("/api/relay/config");
    if (!resp.ok) {
      setStatus("Could not get a token.");
      return;
    }
    const cfg = (await resp.json()) as { token: string; destination: string };

    setStatus("Connecting...");
    client = await SignalWire.SignalWire({ token: cfg.token });
    call = await client.dial({
      to: cfg.destination,
      audio: true,
      video: false,
      rootElement: refs.rootEl,
    });
    call.on("destroy", () => {
      setStatus("Call ended.");
      call = null;
    });
    await call.start(); // WHY await: media negotiates before we report in-call.
    setStatus("In call with Buddy. Say hello!");
  } catch (e) {
    setStatus("Call failed.");
    console.error(e);
  }
}

export async function hangup(): Promise<void> {
  if (call) await call.hangup();
}
