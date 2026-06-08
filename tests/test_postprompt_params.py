"""The shared post-prompt helper must enable conversation + SWML-var capture."""
from python.steps.step11_complete import CompleteAgent


def test_complete_agent_enables_conversation_and_swml_vars():
    agent = CompleteAgent(route="/step11")
    params = agent._params  # SDK stores set_params() values here
    assert params.get("swaig_post_conversation") is True
    assert params.get("swaig_post_swml_vars") is True
