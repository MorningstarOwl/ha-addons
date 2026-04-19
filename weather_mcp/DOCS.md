# Weather MCP

A voice-friendly MCP server that exposes your local weather to Home Assistant's
AI assistants. It reads your location automatically from Home Assistant and
returns forecasts as plain spoken English — no markdown, no symbols —
making it ideal for Assist and TTS pipelines.

## Prerequisites

A free [OpenWeatherMap API key](https://openweathermap.org/api). The free tier
covers the Current Weather and 5-Day Forecast endpoints used here.

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and paste `https://github.com/MorningstarOwl/ha-addons`
2. Install **Weather MCP** from the store.
3. Go to the **Configuration** tab and fill in:
   - `owm_api_key`: your OpenWeatherMap API key
   - `units`: `imperial` (°F) or `metric` (°C)
   - `location` *(optional)*: zip code (e.g. `84101`) or city/state (e.g. `Salt Lake City, UT`).
     Leave blank to use the location set in Home Assistant automatically.
4. Start the addon.

## Connecting to Home Assistant

Add the MCP integration in Home Assistant:
**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:
```
http://homeassistant.local:8765/sse
```

The integration exposes a single tool `get_weather` that your AI assistant
can call to get current conditions and a 3-day forecast.

## Example output

> Right now it's 68 degrees with partly cloudy skies, feeling like 65.
> Humidity is 52 percent and winds are 8 miles per hour.
> Looking ahead — Tuesday: light rain, high of 71, low of 58.
> Wednesday: mostly cloudy, high of 66, low of 54.
> Thursday: clear skies, high of 74, low of 60.
