#!/usr/bin/env python
"""Pre-flight: run every SWAIG function's shared test case before a workshop.

Usage:
  python scripts/swaig_preflight.py              # run all (route, function) pairs
  python scripts/swaig_preflight.py --offline-only  # skip network functions

Exits non-zero if any function fails. For deep single-function debugging, use the
Agents SDK CLI directly, e.g.:  swaig-test main.py --exec tell_joke
"""
import sys
sys.path.insert(0, ".")


def _is_network(name, route):
    """Functions that hit live external APIs (skipped under --offline-only).

    get_weather always calls Open-Meteo. tell_joke calls icanhazdadjoke.com on
    every route except /step06, the hardcoded-list version.
    """
    if name == "get_weather":
        return True
    return name == "tell_joke" and route != "/step06"


def main_cli():
    offline = "--offline-only" in sys.argv
    import main  # safe: server.run() is guarded; this builds + registers agents

    # Drive off the health store (single source of truth shared with the
    # dashboard), but only test functions actually owned by a live agent in
    # this process. STORE.load() can replay stale entries from a prior run's
    # .workshop_function_health.json; those phantoms have no owning agent and
    # must not produce spurious FAILs at workshop time.
    targets = [
        (f["route"], f["name"], f.get("kind", "tool"))
        for f in main.function_health.STORE.all()
        if f.get("route") in main.registered_agents
        and f["name"] in getattr(main.registered_agents[f["route"]]._tool_registry,
                                 "_swaig_functions", {})
    ]
    if not targets:
        print("No SWAIG functions registered.")
        sys.exit(1)

    failures = skipped = 0
    print(f"{'ROUTE':<10}{'FUNCTION':<20}{'KIND':<8}{'RESULT':<8}{'ms':<7}DETAIL")
    print("-" * 84)
    for route, name, kind in targets:
        if offline and _is_network(name, route):
            skipped += 1
            print(f"{route:<10}{name:<20}{kind:<8}{'SKIP':<8}{'-':<7}skipped (--offline-only)")
            continue
        r = main.run_swaig_case(name, route)
        ok = r.get("ok")
        if not ok:
            failures += 1
        ms = r.get("latency_ms")
        detail = str(r.get("result", ""))[:38].replace("\n", " ")
        print(f"{route:<10}{name:<20}{kind:<8}{('PASS' if ok else 'FAIL'):<8}"
              f"{(str(ms) if ms is not None else '-'):<7}{detail}")
    print("-" * 84)
    tested = len(targets) - skipped
    print(f"{tested - failures}/{tested} passed" + ("  (network functions skipped)" if offline else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main_cli()
