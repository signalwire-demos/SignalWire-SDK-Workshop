---
name: Deployment publish blockers (this repl)
description: Two non-obvious causes of failed publishes here — invalid dotreplit deploymentTarget value, and live secrets in gitignored runtime files getting bundled into the deploy security scan.
---

# Deployment publish blockers

## 1. `deploymentTarget` must be a schema-valid value
- Symptom: "Failed to fetch deployment configuration: Unable to validate dotreplit schema", and/or builds that run the Security Scan then die immediately afterward with NO build-command output (~13s).
- Cause: `.replit` `[deployment] deploymentTarget` was set to `"reserved_vm"`, which is NOT a valid schema value.
- Fix: valid values are `autoscale`, `vm`, `scheduled`, `static`. For an always-on Reserved VM use `"vm"`. Set it via the `deployConfig` callback (cannot edit `.replit` deploy block directly).
- **Why:** an invalid target fails config validation; the build can pass the scan step then abort before `pip install .` ever runs, which looks like a security-scan failure but isn't.

## 2. Replit deploy security scan bundles gitignored runtime files
- Symptom: build fails at/after "Security Scan" with no runtime/deployment logs; local `runDependencyAudit`/`runSastScan`/`runHoundDogScan` all come back clean (they only scan git-tracked files).
- Cause: the deploy bundle/secret-scan includes the WHOLE workspace filesystem, including gitignored files. Here a live SignalWire token (`PT`+40 hex) lived in the gitignored runtime file `.workshop_sessions.json`.
- Fix: delete the leftover dev runtime state before publishing. In this app those are `.workshop_*.json` and `calls/*.json` — all gitignored, all regenerated fresh at runtime, and per the README prod is per-attendee (each user enters their own creds in-browser; do NOT set `SIGNALWIRE_*` secrets on the deployment).
- **Why:** a clean git-tracked scan does NOT mean a clean deploy; check gitignored runtime/state files for real credentials before publishing.
- **How to apply:** `grep -rlE 'PT[0-9a-f]{40}' . --include='*.json'` (or the relevant secret pattern) to find live tokens on disk, including gitignored ones.
