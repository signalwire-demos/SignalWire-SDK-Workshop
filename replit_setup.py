"""
Replit workshop setup - URL detection and optional-secret validation.

Called by main.py before importing the SDK. Detects the Replit public URL
and reports the status of optional API keys.
"""

import os


# Every workshop function uses keyless APIs (icanhazdadjoke.com for jokes,
# Open-Meteo for weather), so no third-party API secrets are required.
# SignalWire credentials are entered per-attendee in the browser wizard.
OPTIONAL_SECRETS = []

AUTH_USER_DEFAULT = "workshop"
AUTH_PASS_DEFAULT = "password"


def startup():
    """Detect URL, set auth defaults, report secret status.

    Returns (base_url, auth_user, auth_password).
    """
    # 1. Set the public URL for webhook generation.
    # Precedence:
    #   1. explicit SWML_PROXY_URL_BASE override (forks / custom domains)
    #   2. PUBLISHED DEPLOYMENT -> the stable *.replit.app deploy URL. A VM
    #      deployment may still have REPLIT_DEV_DOMAIN set, but that
    #      *.worf.replit.dev host is alive only while the editor is open. If it
    #      leaks into the webhook URLs baked into SWML, every SignalWire
    #      callback (post_prompt, SWAIG, debug_events) 404s once the editor
    #      closes. So in a deployment we ALWAYS pin the public deploy URL.
    #   3. dev (editor) -> the per-repl dev domain, reachable now.
    #   4. fallback -> the deploy URL.
    DEPLOY_URL = "https://signalwire-workshop.replit.app"
    override = os.getenv("SWML_PROXY_URL_BASE")
    is_deployment = bool(os.getenv("REPLIT_DEPLOYMENT"))
    dev_domain = os.getenv("REPLIT_DEV_DOMAIN")

    if override:
        base_url = override
        print(f"Using SWML_PROXY_URL_BASE from env: {base_url}")
    elif is_deployment:
        base_url = DEPLOY_URL
        os.environ["SWML_PROXY_URL_BASE"] = base_url
        print(f"Published deployment - pinning public deploy URL: {base_url}")
    elif dev_domain:
        base_url = f"https://{dev_domain}"
        os.environ["SWML_PROXY_URL_BASE"] = base_url
        print(f"Using Replit dev domain: {base_url}")
    else:
        base_url = DEPLOY_URL
        os.environ["SWML_PROXY_URL_BASE"] = base_url
        print(f"Using fallback deploy URL: {base_url}")

    # 2. Set auth defaults
    os.environ.setdefault("SWML_BASIC_AUTH_USER", AUTH_USER_DEFAULT)
    os.environ.setdefault("SWML_BASIC_AUTH_PASSWORD", AUTH_PASS_DEFAULT)
    auth_user = os.environ["SWML_BASIC_AUTH_USER"]
    auth_pass = os.environ["SWML_BASIC_AUTH_PASSWORD"]

    # 3. Report optional secrets
    print("\n" + "=" * 60)
    print("  SignalWire SDK Workshop - AI Phone Agent")
    print("=" * 60)

    if OPTIONAL_SECRETS:
        print("\nOptional API keys (add via Replit Secrets tab):")
        for var, desc in OPTIONAL_SECRETS:
            val = os.getenv(var, "")
            if val:
                masked = "*" * max(0, len(val) - 4) + val[-4:]
                print(f"  [ok] {var} = {masked}")
            else:
                print(f"  [--] {var} - {desc}")
    else:
        print("\nNo third-party API keys required (all workshop APIs are keyless).")

    return base_url, auth_user, auth_pass
