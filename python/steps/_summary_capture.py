"""Shared post-prompt capture so every step agent records calls identically."""
from call_store import STORE


def record_call(agent, raw_data):
    name = agent.get_name() if hasattr(agent, "get_name") else getattr(agent, "name", "unknown")
    route = getattr(agent, "route", None)
    STORE.record(name, route, raw_data)
