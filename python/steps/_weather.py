"""Shared server-side weather tool (Open-Meteo, keyless, no prerequisites).

Registered as a normal SWAIG function via define_tool (runs on our server),
NOT as a serverless DataMap. A real workshop call proved SignalWire's serverless
DataMap engine left every ${...} variable empty for this function, so we fetch +
format here where the behavior is deterministic and debuggable.

Open-Meteo (vs wttr.in): it is built for programmatic access — no API key, no
User-Agent quirks, and generous rate limits — so it stays reliable from a shared
Replit datacenter IP under concurrent workshop load. Lookup is two calls:
geocode the city name to lat/lon, then fetch the current conditions.
"""
import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes -> spoken description.
# https://open-meteo.com/en/docs (WMO Weather interpretation codes)
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Freezing fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorms", 96: "Thunderstorms with hail", 99: "Thunderstorms with heavy hail",
}


def fetch_weather(city):
    """Return a spoken-friendly weather string for `city`, or a graceful fallback.

    Pure function (no SDK types) so it can be unit-tested directly.
    """
    city = (city or "").strip()
    if not city:
        return "Which city would you like the weather for?"
    try:
        geo = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=8)
        geo.raise_for_status()
        results = geo.json().get("results") or []
        if not results:
            return f"Sorry, I couldn't find a place called {city}. Please try another city."
        loc = results[0]
        place = loc.get("name") or city
        forecast = requests.get(
            FORECAST_URL,
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code",
                "temperature_unit": "fahrenheit",
            },
            timeout=8,
        )
        forecast.raise_for_status()
        current = forecast.json().get("current") or {}
    except (requests.RequestException, ValueError, KeyError):
        return f"Sorry, I couldn't reach the weather service for {city}. Please try again."

    temp = current.get("temperature_2m")
    if temp is None:
        return f"Sorry, I couldn't get the weather for {city} right now. Please try again."
    desc = _WMO.get(current.get("weather_code"))
    humidity = current.get("relative_humidity_2m")
    feels = current.get("apparent_temperature")

    lead = f"Weather in {place}: " + (f"{desc}, " if desc else "")
    parts = [f"{round(temp)} degrees Fahrenheit"]
    if humidity is not None:
        parts.append(f"humidity {round(humidity)} percent")
    sentence = lead + ", ".join(parts) + "."
    if feels is not None:
        sentence += f" Feels like {round(feels)} degrees."
    return sentence


def register_weather_tool(agent, advance_to_step=None, live_emit=False):
    """Register get_weather as a server-side SWAIG function on `agent`.

    advance_to_step: if set, the handler forces a step change to that step
    after fetching weather (SwaigFunctionResult.swml_change_step). No workshop
    agent passes it anymore — step11's topic step delivers the result in-step —
    but the capability is kept (and unit-tested) as a reference for forcing
    governed transitions from a tool handler.
    live_emit: if True, emits a live_events.BUS event after each fetch (used by
    step11 only; step08/09/10 callers leave this False so they emit nothing).
    """
    def handler(args, raw_data):
        from signalwire_agents import SwaigFunctionResult
        city = (args or {}).get("city")
        try:
            out = fetch_weather(city)
            if live_emit:
                import live_events
                live_events.BUS.emit("swaig", "get_weather", {"city": city, "result": out[:80]})
        except Exception as e:
            if live_emit:
                import live_events
                live_events.BUS.emit("swaig", "get_weather", {"city": city, "error": str(e)[:80]})
            raise
        result = SwaigFunctionResult(out)
        if advance_to_step:
            result.swml_change_step(advance_to_step)
        return result

    agent.define_tool(
        name="get_weather",
        description=(
            "Get the current weather for a city. Use this when the caller asks "
            "about weather, temperature, or conditions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city to get weather for"}
            },
            "required": ["city"],
        },
        handler=handler,
        fillers={
            "en-US": [
                "Let me check the forecast...",
                "One moment, pulling up the weather...",
            ]
        },
    )
