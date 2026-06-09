#!/usr/bin/env python
"""Pre-flight: run every SWAIG function's shared test case before a workshop.

Usage:
  python scripts/swaig_preflight.py              # run all functions
  python scripts/swaig_preflight.py --offline-only  # skip network functions (get_weather)

Exits non-zero if any function fails. For deep single-function debugging, use the
Agents SDK CLI directly, e.g.:  swaig-test main.py --exec tell_joke
"""
import sys
sys.path.insert(0, ".")

NETWORK_FUNCS = {"get_weather"}  # hits a live weather API


def main_cli():
    offline = "--offline-only" in sys.argv
    import main  # safe: server.run() is guarded; this builds + registers agents

    # Drive off the health store (single source of truth shared with the
    # dashboard), but only test functions actually owned by a live agent in
    # this process. STORE.load() can replay stale entries from a prior run's
    # .workshop_function_health.json; those phantoms have no owning agent and
    # must not produce spurious FAILs at workshop time.
    names = [
        f["name"]
        for f in main.function_health.STORE.all()
        if main._owning_agent(f["name"])[1] is not None
    ]
    if not names:
        print("No SWAIG functions registered.")
        sys.exit(1)

    failures = 0
    print(f"{'FUNCTION':<20}{'RESULT':<8}{'ms':<7}DETAIL")
    print("-" * 72)
    for name in names:
        if offline and name in NETWORK_FUNCS:
            print(f"{name:<20}{'SKIP':<8}{'-':<7}skipped (--offline-only)")
            continue
        r = main.run_swaig_case(name)
        ok = r.get("ok")
        if not ok:
            failures += 1
        ms = r.get("latency_ms")
        detail = str(r.get("result", ""))[:44].replace("\n", " ")
        print(f"{name:<20}{('PASS' if ok else 'FAIL'):<8}{(str(ms) if ms is not None else '-'):<7}{detail}")
    print("-" * 72)
    tested = len(names) - (len(NETWORK_FUNCS & set(names)) if offline else 0)
    print(f"{tested - failures}/{tested} passed" + ("  (network functions skipped)" if offline else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main_cli()
