# tests/test_agent_graph.py
import sys
sys.path.insert(0, ".")


def test_build_graph_from_complete_agent():
    import agent_graph
    from python.steps.step11_complete import CompleteAgent
    g = agent_graph.build_graph(CompleteAgent(route="/step11"))
    assert g["initial_step"] == "greeting"
    by_name = {s["name"]: s for s in g["steps"]}
    assert set(by_name["greeting"]["valid_steps"]) == {
        "weather", "joke", "time", "math", "wrap_up"}
    assert by_name["weather"]["functions"] == ["get_weather"]
    # set_functions("none") must normalize to an empty list, not "none"
    assert by_name["greeting"]["functions"] == []
    assert by_name["wrap_up"]["valid_steps"] == []


def test_build_graph_flat_prompt_agent():
    import agent_graph

    class _Flat:  # agent with no contexts/steps state machine
        def _render_swml(self):
            return '{"sections": {"main": [{"ai": {"prompt": {"text": "hi"}}}]}}'

    g = agent_graph.build_graph(_Flat())
    assert g == {"initial_step": None, "steps": []}
