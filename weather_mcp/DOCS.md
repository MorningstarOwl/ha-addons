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
   - `timezone`: select your local timezone from the dropdown. This ensures
     day boundaries (today vs. tomorrow) are calculated correctly for your
     location. Defaults to `America/Denver`.
   - `location` *(optional)*: your location as a **zip code** (e.g. `84101`).
     Leave blank to use the location set in Home Assistant automatically.
     > **Note:** Zip codes are the only reliably supported format. City/state strings
     > (e.g. `Salt Lake City, UT`) may not resolve correctly due to how
     > OpenWeatherMap's geocoding API parses them.
4. Start the addon.

## Connecting to Home Assistant

Add the MCP integration in Home Assistant:
**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:
```
http://homeassistant.local:8765/sse
```

The integration exposes a single tool `get_weather` that your AI assistant
can call to get current conditions, today's forecast high/low, and a
3-day outlook.

## Timezone Reference

The dropdown covers ~76 common timezones across all regions. If your timezone
isn't listed, please [open an issue](https://github.com/MorningstarOwl/ha-addons/issues)
and it can be added in the next release.

| Region | Example zones |
|---|---|
| US & Canada | New York, Chicago, Denver, Los Angeles, Phoenix, Anchorage, Honolulu, Halifax, and more |
| Latin America | Mexico City, São Paulo, Buenos Aires, Santiago, Bogotá, Lima |
| Europe | London, Paris, Berlin, Rome, Madrid, Moscow, Istanbul, and more |
| Africa | Cairo, Johannesburg, Lagos, Nairobi, Casablanca |
| Asia | Dubai, Karachi, Kolkata, Bangkok, Singapore, Tokyo, Seoul, Shanghai, and more |
| Pacific | Sydney, Melbourne, Brisbane, Perth, Auckland, Fiji |

## Example output

> Today's forecast: partly cloudy, high of 68, low of 44. Right now it's 61
> degrees with partly cloudy skies, feeling like 58. Humidity is 52 percent
> and winds are 8 miles per hour. Looking ahead — Wednesday: light rain,
> high of 71, low of 58. Thursday: mostly cloudy, high of 66, low of 54.
> Friday: clear skies, high of 74, low of 60.
