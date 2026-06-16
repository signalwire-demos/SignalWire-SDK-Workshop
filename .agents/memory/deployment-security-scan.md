---
name: Deployment security scan & .replit schema gotchas
description: Why a Replit publish can fail at the Security Scan phase, and a .replit deploymentTarget value that breaks schema validation.
---

# Deployment Security Scan blocks on filesystem secrets (gitignore does NOT protect you)

The Replit publish pipeline runs a **Security Scan** phase *before* the build command
(`pip install .` etc.) ever runs. If that scan finds secrets, the build fails with only
~4 log lines ending at "Security Scan Complete" and **no build-command output** — that
empty-tail signature means the scan gated the build, not the build command.

**Why:** the deployment snapshots the *workspace filesystem*, not git. `.gitignore` does
**not** exclude a file from the snapshot or the scan. Ephemeral runtime-state files that
capture credentials during local testing (here: `.workshop_sessions.json` holding
`SIGNALWIRE_TOKEN`/`SIGNALWIRE_PROJECT_ID`/`SIGNALWIRE_SPACE`) will trip the scan even
though they are gitignored.

**How to apply:** when a publish fails at the Security Scan step, look for secret-bearing
files physically present in the workspace (especially app-written JSON/state caches),
not just tracked files. Remove them before publishing. Note the in-repl
`runHoundDogScan()`/`runDependencyAudit()` did NOT flag these JSON data files — the
deployment scan is stricter than the local scanners, so a clean local scan is not proof.

**Recurrence risk:** if the app re-writes raw tokens to a snapshot-scanned path at
runtime (e.g. a SessionStore persisting plaintext credentials to project root), the next
publish after any real session will fail again. Durable fix is to stop persisting raw
secrets into the workspace snapshot; deleting the files is only a point-in-time fix.

# .replit deploymentTarget must be schema-valid ("vm", not "reserved_vm")

A `deploymentTarget = "reserved_vm"` in `.replit` fails dotreplit schema validation
(`DOT_REPLIT_SYNTAX_ERROR`, "Unable to validate dotreplit schema"). When the whole
`.replit` fails validation, `listWorkflows()` returns empty and `configureWorkflow`'s
port-forward setup fails. Use `deployConfig({deploymentTarget:"vm", ...})` to write a
valid value — `"vm"` is the always-on reserved instance (build provider reports `gce`).
