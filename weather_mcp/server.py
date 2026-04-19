"""
Weather MCP Server
------------------
Reads options from /data/options.json (injected by HA Supervisor),
pulls lat/lon from the HA REST API using SUPERVISOR_TOKEN,
queries OpenWeatherMap for current conditions and a 3-day forecast,
and returns everything as plain spoken English suitable for TTS read-back.

MCP SSE endpoint: http://homeassistant.local:8765/sse
"""

import json
import os
import logging
from collections import defaultdict, Counter
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
OWM_BASE = "https://api.openweathermap.org/data/2.5"
PORT = 8765


# ---------------------------------------------------------------------------
# Load addon options
# ---------------------------------------------------------------------------

def load_options() -> dict:
    try:
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not read options.json: {e}")
        return {}


options = load_options()
API_KEY: str = options.get("owm_api_key", "").strip()
UNITS: str = options.get("units", "imperial")
UNIT_WORD: str = "Fahrenheit" if UNITS == "imperial" else "Celsius"
UNIT_ABBR: str = "F" if UNITS == "imperial" else "C"


# ---------------------------------------------------------------------------
# Pull lat/lon from HA supervisor API (called lazily per request)
# ---------------------------------------------------------------------------

def get_ha_location() -> tuple[float | None, float | None]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        log.warning("SUPERVISOR_TOKEN not set — location unavailable.")
        return None, None
    try:
        r = httpx.get(
            "http://supervisor/core/api/config",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is not None and lon is not None:
            log.info(f"Location from HA: {lat}, {lon}")
        return lat, lon
    except Exception as e:
        log.warning(f"Could not fetch HA location: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Condition mapping — OWM descriptions → spoken English
# ---------------------------------------------------------------------------

CONDITION_MAP = {
    "clear sky":                      "clear skies",
    "few clouds":                     "mostly clear",
    "scattered clouds":               "partly cloudy",
    "broken clouds":                  "mostly cloudy",
    "overcast clouds":                "overcast",
    "light rain":                     "light rain",
    "moderate rain":                  "moderate rain",
    "heavy intensity rain":           "heavy rain",
    "very heavy rain":                "heavy rain",
    "extreme rain":                   "heavy rain",
    "freezing rain":                  "freezing rain",
    "light intensity drizzle":        "light drizzle",
    "drizzle":                        "drizzle",
    "thunderstorm":                   "thunderstorms",
    "thunderstorm with light rain":   "thunderstorms",
    "thunderstorm with rain":         "thunderstorms",
    "thunderstorm with heavy rain":   "severe thunderstorms",
    "snow":                           "snow",
    "light snow":                     "light snow",
    "heavy snow":                     "heavy snow",
    "sleet":                          "sleet",
    "rain and snow":                  "rain and snow mix",
    "mist":                           "mist",
    "smoke":                          "smoky",
    "haze":                           "haze",
    "dust":                           "dusty",
    "fog":                            "fog",
    "sand":                           "sandy",
    "ash":                            "volcanic ash",
    "squall":                         "squalls",
    "tornado":                        "tornado conditions",
}

DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
]


def spoken_condition(raw: str) -> str:
    return CONDITION_MAP.get(raw.lower(), raw.lower())


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Weather MCP Server")


@mcp.tool()
def get_weather() -> str:
    """
    Returns the current weather conditions and a 3-day forecast
    as a natural spoken-English summary, suitable for voice read-back.
    """
    if not API_KEY:
        return (
            "Weather is unavailable. "
            "Please enter your OpenWeatherMap API key in the addon configuration."
        )

    lat, lon = get_ha_location()
    if lat is None or lon is None:
        return (
            "Weather is unavailable. "
            "Could not determine your location from Home Assistant."
        )

    params = {
        "lat": lat,
        "lon": lon,
        "appid": API_KEY,
        "units": UNITS,
    }

    try:
        with httpx.Client(timeout=10) as client:
            current_r = client.get(f"{OWM_BASE}/weather", params=params)
            current_r.raise_for_status()
            current = current_r.json()

            forecast_r = client.get(
                f"{OWM_BASE}/forecast",
                params={**params, "cnt": 40},  # ~5 days of 3-hour slots
            )
            forecast_r.raise_for_status()
            forecast = forecast_r.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return "Weather is unavailable. The OpenWeatherMap API key appears to be invalid."
        log.error(f"OWM HTTP error: {e}")
        return "Weather data is temporarily unavailable. Please try again in a moment."
    except Exception as e:
        log.error(f"OWM request failed: {e}")
        return "Weather data is temporarily unavailable. Please try again in a moment."

    # ── Current conditions ──────────────────────────────────────────────────
    curr_temp  = round(current["main"]["temp"])
    curr_feels = round(current["main"]["feels_like"])
    curr_cond  = spoken_condition(current["weather"][0]["description"])
    curr_humid = round(current["main"]["humidity"])
    wind_speed = round(current["wind"]["speed"])
    wind_unit  = "miles per hour" if UNITS == "imperial" else "meters per second"

    current_str = (
        f"Right now it's {curr_temp} degrees with {curr_cond}, "
        f"feeling like {curr_feels}. "
        f"Humidity is {curr_humid} percent "
        f"and winds are {wind_speed} {wind_unit}."
    )

    # ── Aggregate forecast into daily buckets ───────────────────────────────
    today = datetime.now(timezone.utc).date()
    daily: dict = defaultdict(lambda: {"highs": [], "lows": [], "conds": []})

    for slot in forecast.get("list", []):
        slot_date = datetime.fromtimestamp(slot["dt"], tz=timezone.utc).date()
        if slot_date == today:
            continue  # today is covered by current conditions
        daily[slot_date]["highs"].append(slot["main"]["temp_max"])
        daily[slot_date]["lows"].append(slot["main"]["temp_min"])
        daily[slot_date]["conds"].append(slot["weather"][0]["description"])

    # ── Build forecast sentences ────────────────────────────────────────────
    forecast_parts: list[str] = []
    for date in sorted(daily.keys())[:3]:
        d = daily[date]
        high = round(max(d["highs"]))
        low  = round(min(d["lows"]))
        top_cond = Counter(d["conds"]).most_common(1)[0][0]
        cond = spoken_condition(top_cond)
        day_name = DAY_NAMES[date.weekday()]
        forecast_parts.append(
            f"{day_name}: {cond}, high of {high}, low of {low}."
        )

    if forecast_parts:
        forecast_str = " ".join(forecast_parts)
        return f"{current_str} Looking ahead — {forecast_str}"
    else:
        return current_str


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not API_KEY:
        log.warning(
            "No OWM API key configured. "
            "Set it in the addon Configuration tab to enable weather data."
        )

    log.info(f"Starting Weather MCP SSE server on port {PORT}...")
    mcp.run(transport="sse", host="0.0.0.0", port=PORT)
