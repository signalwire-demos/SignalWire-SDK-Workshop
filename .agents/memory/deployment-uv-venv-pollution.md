---
name: deployment uv venv pollution
description: Why Replit Python deploy builds fail at "Installing packages" with a Nix-store permission-denied, and how to fix it.
---

# uv sync fails in deploy build: Permission denied writing to /nix/store python

**Symptom:** Publish gets past Security Scan, then fails at "Installing packages":
`error: Failed to install: <pkg>.whl ... failed to create directory /nix/store/...python3-.../lib/python3.11/site-packages/...: Permission denied (os error 13)`.

**Root cause:** The deploy build runs `uv sync` (triggered by presence of `uv.lock` +
pyproject). With `UV_PROJECT_ENVIRONMENT=/home/runner/workspace/.pythonlibs` and
`UV_PYTHON_PREFERENCE=only-system`, uv installs into the venv at `.pythonlibs`. If
`.pythonlibs` already exists in the workspace snapshot as a NON-venv directory (no
`pyvenv.cfg`) — e.g. polluted by a prior `pip install .` using `PYTHONUSERBASE=.pythonlibs`
— uv will NOT create a fresh venv there and falls back to the read-only system Nix Python,
causing the permission error.

**Diagnostic tell:** Successful build logs print `Creating virtual environment at: .pythonlibs`.
Failed build logs are MISSING that line — uv never created the venv.

**Fix:** Delete the polluted dirs so the snapshot is clean and uv recreates a proper venv:
`rm -rf .pythonlibs .venv && uv sync`. Confirm `.pythonlibs/pyvenv.cfg` now exists (valid
venv). Then restart the workflow and verify the app still serves before re-publishing.

**Why:** Deployment snapshots the whole filesystem (gitignore does NOT exclude it), so a
gitignored-but-present `.pythonlibs`/`.venv` from local debugging gets shipped and breaks the
build. Avoid `pip install .` for local debugging on uv-managed Python projects — it pollutes
`.pythonlibs`. Use the package-management tools / `uv sync` instead.

**How to apply:** When a Python publish fails at "Installing packages" with a /nix/store
permission-denied, check whether `.pythonlibs` has a `pyvenv.cfg`; if not, rm -rf and uv sync.
