# tests/test_stateflow_renderer.py
"""Contract assertions for the upgraded state-flow renderer."""
import pathlib

JS = pathlib.Path(__file__).resolve().parents[1].joinpath(
    "web", "state-flow.js").read_text(encoding="utf-8")


def test_renderer_accepts_definition_graph():
    assert "function (el, sf, graph)" in JS


def test_renderer_draws_possible_edges_dashed():
    assert "-.->" in JS          # dashed (possible-but-not-taken) edges
    assert "buildFullMermaid" in JS


def test_renderer_distinguishes_visited_nodes():
    assert "unvisited" in JS and "visited" in JS


def test_renderer_keeps_observed_only_fallback():
    assert "buildMermaid" in JS  # legacy path for callers without a graph
