// Step 12: REST pillar - subscriber token + agent provisioning
// (TypeScript sibling, reference-only). Matches python/steps/step12_rest_demo.py.
// Uses fetch against the Fabric REST API; no SignalWire package import needed.

const HANDLER_NAME = "Chicago Roadshow 2026 Agent";
const AGENT_PATH = "/step11";
const DEFAULT_REFERENCE = "roadshow-attendee";

function creds(): { project: string; token: string; space: string } {
  const project = process.env["SIGNALWIRE_PROJECT_ID"];
  const token = process.env["SIGNALWIRE_TOKEN"];
  const space = process.env["SIGNALWIRE_SPACE"];
  if (!project || !token || !space) {
    throw new Error("missing SIGNALWIRE_PROJECT_ID / SIGNALWIRE_TOKEN / SIGNALWIRE_SPACE");
  }
  return { project, token, space };
}

// WHY raw fetch: the Fabric REST API is not exposed by the LaML client.
async function fabric(method: string, path: string, body?: unknown): Promise<any> {
  const { project, token, space } = creds();
  const auth = Buffer.from(`${project}:${token}`).toString("base64");
  const resp = await fetch(`https://${space}${path}`, {
    method,
    headers: {
      Authorization: `Basic ${auth}`,
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`${method} ${path} -> ${resp.status}`);
  return resp.status === 204 ? {} : resp.json();
}

export async function ensureAgentHandler(): Promise<string> {
  const base = (process.env["PUBLIC_BASE"] || process.env["SWML_PROXY_URL_BASE"] || "").replace(/\/$/, "");
  if (!base) throw new Error("no public base URL; set SWML_PROXY_URL_BASE or PUBLIC_BASE");

  const listing = await fabric("GET", "/api/fabric/resources/external_swml_handlers");
  let handlerId: string;
  const existing = (listing.data || []).find((h: any) => h.name === HANDLER_NAME);
  if (existing) {
    handlerId = existing.id;
  } else {
    const created = await fabric("POST", "/api/fabric/resources/external_swml_handlers", {
      name: HANDLER_NAME,
      used_for: "calling",
      primary_request_url: `${base}${AGENT_PATH}`,
      primary_request_method: "POST",
    });
    handlerId = created.id;
  }
  const addrs = await fabric("GET", `/api/fabric/resources/external_swml_handlers/${handlerId}/addresses`);
  return addrs.data[0].channels.audio;
}

export async function mintSubscriberToken(
  reference: string = DEFAULT_REFERENCE
): Promise<{ token: string; subscriberId: string }> {
  const data = await fabric("POST", "/api/fabric/subscribers/tokens", { reference });
  return { token: data.token, subscriberId: data.subscriber_id ?? "" };
}

async function main(): Promise<number> {
  try {
    const address = await ensureAgentHandler();
    console.log("agent dial address:", address);
    const ref = process.env["SUBSCRIBER_REFERENCE"] || DEFAULT_REFERENCE;
    const { token, subscriberId } = await mintSubscriberToken(ref);
    console.log("subscriber_id:", subscriberId);
    console.log("token (masked):", token.slice(0, 12) + "...");
    return 0;
  } catch (e) {
    console.error("[error]", e instanceof Error ? e.message : e);
    return 1;
  }
}

main().then((code) => process.exit(code));
