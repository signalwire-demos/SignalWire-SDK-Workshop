# Deploying to Replit (production)

This app is **stateful and single-process**: per-session credentials, captured
calls, and the admin feed live in memory + local JSON, and `/admin/stream` is a
long-lived SSE connection. Deploy it accordingly.

## 1. Deployment type: Reserved VM (not Autoscale)

`.replit` is set to `deploymentTarget = "reserved_vm"`. **Keep it that way.**

Autoscale runs multiple stateless instances and scales to zero, which breaks
this app three ways:
- SignalWire's callbacks (SWML fetch, SWAIG `get_weather`, `post_prompt`) are
  server-to-server with **no browser cookie**. They could hit a different
  instance than the one that stored the attendee's session → missing
  credentials, calls captured on the wrong instance, a split `/admin` view.
- Scale-to-zero cold starts can time out the SWML fetch when a call arrives.
- The `/admin` SSE stream is tied to one instance; load-balancing/redeploys drop it.

A Reserved VM is a single always-on instance, so production behaves exactly like
the single process used in testing. A small VM (1 vCPU / 2 GB) handles a
workshop room easily.

## 2. Configuration — on the `/admin` page (no Secrets required)

The three connection values are editable directly on the dashboard: open
`/admin` → **⚙ Config**.

| Field | Why | Default |
|---|---|---|
| **Public URL** | Every webhook URL SignalWire calls back (SWML, SWAIG, post_prompt) is built from this. | **Auto-detected** from the address you open `/admin` at (your `*.replit.app` domain) — usually nothing to do. |
| **SWAIG auth username** | Basic-auth user embedded in the provisioned webhook URLs and validated on inbound requests. | `workshop` |
| **SWAIG auth password** | Basic-auth password (same). | `password` — **change it** for a public deployment. |

Saving applies immediately to the live process — it updates both the URLs new
provisioning embeds *and* the credentials the agents validate inbound requests
against. Set these **before** anyone provisions a number (the values are baked
into each session's SWML webhook resource at provisioning time).

**Optional env override:** the same values can still be set as Replit Secrets
(`SWML_PROXY_URL_BASE`, `SWML_BASIC_AUTH_USER`, `SWML_BASIC_AUTH_PASSWORD`); they
act as the fallback when no admin override is set. Precedence is
**admin override → auto-detected → Secret/env → default**.

### SignalWire credentials

The workshop is multi-tenant: each attendee enters **their own** SignalWire
Project ID / API Token / Space in the in-app wizard (stored per browser
session). So the deployment does **not** need global `SIGNALWIRE_*` secrets for
the workshop flow. (Set them only if you want a single-tenant deployment driven
from env — see `.env.example`.)

## 3. State & persistence

State persists durably across redeploys. In a Replit deployment (when
`REPLIT_DB_URL` is present) the stores — sessions, calls, config, errors,
function health — write to the **Replit Key-Value DB** under `workshop:*` keys,
which survives redeploys and restarts. Locally (no `REPLIT_DB_URL`) the same
data is kept in the `.workshop_*.json` files for dev/test.

- A redeploy no longer wipes `/admin` history.
- Raw SignalWire API tokens are still never persisted (only a masked tail).
- To clear data, delete the `workshop:*` keys in the Replit DB pane (or the
  local `.workshop_*.json` files in dev).

## 4. Weather

`get_weather` is a server-side SWAIG tool using **Open-Meteo** (keyless, no
User-Agent quirks, generous limits — reliable from a shared Replit IP under
concurrent load). No configuration or API key needed. Jokes use
icanhazdadjoke.com (also keyless).

## 5. Post-deploy checklist

1. Open `https://<your-app>.replit.app/` — the landing page loads.
2. Open `https://<your-app>.replit.app/admin` — the dashboard loads (unlisted, no auth).
3. In the wizard, enter SignalWire credentials and provision a number.
4. Call the number. Ask for the weather and a joke, then hang up.
5. In `/admin`: confirm the call appears with a real weather result, the
   transcript/tools populate, and it correlates to your session (not "unknown").
6. If anything misbehaves, open the call's **SWAIG Log** tab — it shows each
   function's args, the exact URL hit, the raw response, and any error flags.

## 6. Notes

- The app binds `0.0.0.0` on `$PORT` (default 5000); Reserved VM serves it on 443
  externally. No change needed.
- `/admin` is unlisted with **no authentication** — fine for a short-lived,
  trusted workshop, but add auth before any longer-lived hosting (it exposes
  every attendee's call content and credential metadata, tokens masked).
