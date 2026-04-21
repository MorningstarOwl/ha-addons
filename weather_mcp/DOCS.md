# Weather MCP

A voice-friendly MCP server that delivers current conditions and a 3-day
forecast to Home Assistant's AI assistant. Reads your location automatically
from Home Assistant and returns results as plain spoken English — no markdown,
no symbols — making it ideal for Assist and TTS pipelines.

---

## Prerequisites

A free [OpenWeatherMap API key](https://openweathermap.org/api). The free tier
covers the Current Weather and 5-Day Forecast endpoints used by this addon.

---

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   Paste: `https://github.com/MorningstarOwl/ha-addons`

2. Install **Weather MCP** from the store.

3. Go to the **Configuration** tab and set your options (see below).

4. Start the addon.

---

## Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `owm_api_key` | Yes | — | Your OpenWeatherMap API key. |
| `units` | Yes | `imperial` | `imperial` for °F, `metric` for °C. |
| `location` | No | — | Zip code fallback (e.g. `10001`). Leave blank to use the location set in Home Assistant automatically. |

> **Note on location format:** Zip codes are the only reliably supported
> format for the `location` field. City/state strings (e.g. `New York, NY`)
> may not resolve correctly due to how OpenWeatherMap's geocoding API parses
> free-form text.

---

## Connecting to Home Assistant

Once the addon is running, add the MCP integration:

**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:

```
http://homeassistant.local:8765/sse
```

Or use the HA host's LAN IP directly if mDNS isn't reliable on your network:

```
http://<your-ha-ip>:8765/sse
```

The integration exposes a single tool `get_weather` that your AI assistant
can call to retrieve current conditions and a 3-day forecast.

---

## Example Output

**Prompt:** "What's the weather like?"

> Right now it's 68 degrees with partly cloudy skies, feeling like 65.
> Humidity is 52 percent and winds are 8 miles per hour.
> Looking ahead — Tuesday: light rain, high of 71, low of 58.
> Wednesday: mostly cloudy, high of 66, low of 54.
> Thursday: clear skies, high of 74, low of 60.

---

## Troubleshooting

### "Could not determine location"

The addon could not read a location from Home Assistant and no `location`
option was set. Set a zip code in the **Configuration** tab as a fallback.

### "Invalid API key" or no weather data

Confirm your `owm_api_key` is correct. New OpenWeatherMap keys can take a
few minutes to activate after creation.

### The addon won't start

Check the addon log tab for Python errors. The most common cause is a missing
or malformed `owm_api_key`.
