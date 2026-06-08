"""Tests for the server-side weather tool (python/steps/_weather.py).

get_weather is a define_tool SWAIG function (runs on our server), NOT a
serverless DataMap: a real workshop call proved SignalWire's DataMap engine
left every ${...} empty. These tests exercise the fetch/format logic directly
(no network, Open-Meteo geocode + forecast mocked) and confirm the agent
registers it as a server-side function.
"""
import requests

from python.steps import _weather
from python.steps.step08_weather import WeatherJokeAgent


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_GEO = {"results": [{"name": "Chicago", "latitude": 41.85, "longitude": -87.65}]}
_FORECAST = {
    "current": {
        "temperature_2m": 76.4,
        "relative_humidity_2m": 79,
        "apparent_temperature": 81.0,
        "weather_code": 3,  # Overcast
    }
}


def _mock_open_meteo(monkeypatch, geo=_GEO, forecast=_FORECAST):
    """Route geocode vs forecast calls by URL."""
    def fake_get(url, params=None, timeout=None, headers=None):
        if "geocoding" in url:
            return _FakeResp(geo)
        return _FakeResp(forecast)
    monkeypatch.setattr(requests, "get", fake_get)


def test_fetch_weather_formats_response(monkeypatch):
    _mock_open_meteo(monkeypatch)
    out = _weather.fetch_weather("Chicago")
    assert out == (
        "Weather in Chicago: Overcast, 76 degrees Fahrenheit, "
        "humidity 79 percent. Feels like 81 degrees."
    )


def test_fetch_weather_empty_city_asks_again():
    assert "city" in _weather.fetch_weather("").lower()
    assert "city" in _weather.fetch_weather(None).lower()


def test_fetch_weather_unknown_city(monkeypatch):
    _mock_open_meteo(monkeypatch, geo={"results": []})
    out = _weather.fetch_weather("Zzzznotacity")
    assert "couldn't find" in out and "Zzzznotacity" in out


def test_fetch_weather_handles_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("down")
    monkeypatch.setattr(requests, "get", boom)
    out = _weather.fetch_weather("Chicago")
    assert "Sorry" in out and "Chicago" in out


def test_fetch_weather_handles_missing_current(monkeypatch):
    _mock_open_meteo(monkeypatch, forecast={"current": {}})
    out = _weather.fetch_weather("Chicago")
    assert "Sorry" in out


def test_get_weather_is_server_side_not_datamap():
    agent = WeatherJokeAgent()
    fn = agent._tool_registry._swaig_functions["get_weather"]
    # DataMap functions are stored as raw dicts (with a "data_map" key); a
    # server-side define_tool function is a SWAIGFunction object with a handler.
    assert not isinstance(fn, dict), "get_weather must be a server-side tool, not a DataMap dict"
    assert hasattr(fn, "handler")
