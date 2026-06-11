"""Extract an agent's contexts/steps definition graph from its rendered SWML.

The graph powers the State Flow viewer: every step + every valid_steps edge
("possible paths"), which the frontend overlays with the transitions a call
actually took.
"""
import json


def build_graph(agent):
    """Return {"initial_step": str|None, "steps": [{name, functions, valid_steps}]}.

    Agents without a contexts/steps state machine yield an empty graph.
    """
    swml = agent._render_swml()
    doc = json.loads(swml) if isinstance(swml, str) else swml
    ai = None
    for verb in (doc.get("sections", {}).get("main") or []):
        if isinstance(verb, dict) and "ai" in verb:
            ai = verb["ai"]
            break
    contexts = ((ai or {}).get("prompt") or {}).get("contexts") or {}
    ctx = contexts.get("default") or (next(iter(contexts.values())) if contexts else {})
    steps = []
    for s in (ctx.get("steps") or []):
        fns = s.get("functions")
        steps.append({
            "name": s.get("name"),
            "functions": fns if isinstance(fns, list) else [],
            "valid_steps": s.get("valid_steps") or [],
        })
    return {
        "initial_step": steps[0]["name"] if steps else None,
        "steps": steps,
    }
