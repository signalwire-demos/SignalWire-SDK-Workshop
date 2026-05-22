"""
Replit workshop setup - URL detection and optional-secret validation.

Called by main.py before importing the SDK. Detects the Replit public URL
and reports the status of optional API keys.
"""

import os


OPTIONAL_SECRETS = [
    ("WEATHER_API_KEY", "weatherapi.com - needed for weather (step 8+)"),
    ("API_NINJAS_KEY",  "api-ninjas.com  - needed for live jokes (step 7+)"),
]

AUTH_USER_DEFAULT = "workshop"
AUTH_PASS_DEFAULT = "password"


def startup():
    """Detect URL, set auth defaults, report secret status.

    Returns (base_url, auth_user, auth_password).
    """
    # 1. Set the public URL for webhook generation.
    # Hardcoded to the deployment URL so it works in both dev and production.
    # REPLIT_DEV_DOMAIN points to a stale *.kirk.replit.dev URL that returns
    # 404 in production, so we never use it.
    DEPLOY_URL = "https://chicago-roadshow-2026.replit.app"

    if os.getenv("SWML_PROXY_URL_BASE"):
        base_url = os.getenv("SWML_PROXY_URL_BASE")
        print(f"Using SWML_PROXY_URL_BASE from env: {base_url}")
    else:
        base_url = DEPLOY_URL
        os.environ["SWML_PROXY_URL_BASE"] = base_url
        print(f"Using hardcoded deploy URL: {base_url}")

    # 2. Set auth defaults
    os.environ.setdefault("SWML_BASIC_AUTH_USER", AUTH_USER_DEFAULT)
    os.environ.setdefault("SWML_BASIC_AUTH_PASSWORD", AUTH_PASS_DEFAULT)
    auth_user = os.environ["SWML_BASIC_AUTH_USER"]
    auth_pass = os.environ["SWML_BASIC_AUTH_PASSWORD"]

    # 3. Report optional secrets
    print("\n" + "=" * 60)
    print("  Buddy Workshop - SignalWire AI Phone Agent")
    print("=" * 60)

    print("\nOptional API keys (add via Replit Secrets tab):")
    for var, desc in OPTIONAL_SECRETS:
        val = os.getenv(var, "")
        if val:
            masked = "*" * max(0, len(val) - 4) + val[-4:]
            print(f"  [ok] {var} = {masked}")
        else:
            print(f"  [--] {var} - {desc}")

    return base_url, auth_user, auth_pass
