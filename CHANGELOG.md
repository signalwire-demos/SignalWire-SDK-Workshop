# Changelog

All notable changes to the Chicago Roadshow 2026 SignalWire workshop are documented here.

## 2026-05-28

Inbound phone calls now reach the AI agent, and the REST + RELAY pillars run on
SWML resources and the SignalWire REST API only — no compatibility/LaML/cXML.

### Fixed

- **Inbound calls now reach the agent.** Provisioned numbers were configured as
  cXML/LaML voice webhooks (`voice_url`), so SignalWire fetched the agent route
  expecting cXML and got a `404 / 11200 HTTP retrieval failure`. Numbers are now
  assigned to an **SWML webhook resource** as a phone route, matching the
  dashboard's "Assign Resource → SWML Script (External URL)" flow.
- **The SWML webhook now returns valid SWML JSON.** Two causes, both fixed:
  - The webhook's `primary_request_url` now embeds the agent's Basic-auth
    credentials (`https://workshop:password@…/stepNN`). Without them SignalWire
    received `401 Unauthorized` instead of SWML.
  - The public base URL now resolves to the live, per-repl `REPLIT_DEV_DOMAIN`
    instead of the hardcoded `chicago-roadshow-2026.replit.app`, which returned
    Replit's "app isn't live yet" 404 page and was not portable to forks.

### Changed

- **Migrated the entire REST/provisioning layer to the SignalWire Agents SDK
  REST client** (`signalwire_agents.rest.client.SignalWireClient`). Phone-number
  search / buy / list / lookup go through `client.phone_numbers.*`; SWML
  resources, phone-route assignment, and subscriber tokens go through
  `client.fabric.*`.
- **Switched to the canonical `swml_webhooks` Fabric resource**
  (`POST /api/fabric/resources/swml_webhooks`), replacing the legacy
  `external_swml_handlers` path.
- `replit_setup.py` URL precedence is now: explicit `SWML_PROXY_URL_BASE`
  override → `REPLIT_DEV_DOMAIN` (live, per-repl) → published-deployment
  fallback. Removed the hardcoded `SWML_PROXY_URL_BASE` from `.replit`.
- Phone-route assignment is idempotent, so repointing a number to a different
  step no longer errors and heals a number that was saved but never assigned.

### Removed

- **All compatibility / LaML / cXML API usage** — `signalwire.rest.Client`,
  `incoming_phone_numbers`, `available_phone_numbers`, `voice_url`, and the
  hand-rolled raw-HTTPS `_fabric()` helper. The workshop now uses SWML + the
  SignalWire REST API only.
- The `signalwire>=2.0` dependency (the compatibility SDK is no longer used).
- The dead `@signalwire/node` TypeScript types shim.

### Docs

- README step 12, the landing-page SDK badges, and the TypeScript reference
  siblings now describe the SDK/SWML calls (`client.phone_numbers.*`,
  `client.fabric.swml_webhooks.*`) instead of LaML.
