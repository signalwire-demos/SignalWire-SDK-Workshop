"""
Structural tests for the Step 8 weather DataMap.

These assert the generated SWAIG function is a SHAPE DataMap can actually
execute. DataMap runs multiple webhooks as sequential *fallbacks*, not as a
geocode -> forecast pipeline, and there is no way to feed one webhook's
response into the next webhook's request. So a correct weather lookup must be
a SINGLE webhook (an API that takes the city name directly) with its output
attached to that webhook.

No network or SignalWire calls here -- we only inspect the generated dict.

Run from the project root:
    pytest tests/test_weather_datamap.py -v
"""

from python.steps.step08_weather import WeatherJokeAgent


def _get_weather_data_map():
    agent = WeatherJokeAgent()
    fn = agent._tool_registry._swaig_functions["get_weather"]
    return fn["data_map"]


def test_weather_uses_single_webhook():
    # DataMap can't chain webhooks: extra webhooks are fallbacks, not steps.
    webhooks = _get_weather_data_map()["webhooks"]
    assert len(webhooks) == 1, (
        f"expected exactly one webhook, got {len(webhooks)} "
        "(multiple webhooks are fallbacks, not a geocode->forecast chain)"
    )


def test_weather_webhook_has_output_attached():
    # .output() attaches to the LAST webhook; if the executed webhook has no
    # output, the caller gets nothing usable.
    webhook = _get_weather_data_map()["webhooks"][0]
    assert "output" in webhook, "the weather webhook must carry its own output template"


def test_weather_webhook_does_not_reference_a_prior_response():
    # ${response...} only resolves against the current webhook's own response.
    # A URL referencing a prior webhook's response can never be filled in.
    url = _get_weather_data_map()["webhooks"][0]["url"]
    assert "${response" not in url, (
        "webhook URL references a prior webhook response, which DataMap "
        f"cannot resolve: {url}"
    )
    assert "${args.city}" in url or "${enc:args.city}" in url, (
        "weather webhook should look up the caller-provided city directly"
    )
