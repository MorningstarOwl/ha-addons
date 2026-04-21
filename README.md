# MorningstarOwl HA Addons

Custom Home Assistant addon repository.

## Addons

### Weather MCP

A voice-friendly MCP server for Home Assistant's AI assistant integration.
Uses OpenWeatherMap to deliver current conditions and a 3-day forecast as
plain spoken English — no markdown, no symbols.

Location is read automatically from Home Assistant. If that fails, you can
set a **zip code** (e.g. `84101`) in the addon Configuration tab as a fallback.
City/state strings are not reliably supported by the OpenWeatherMap geocoding API.

See [weather_mcp/DOCS.md](weather_mcp/DOCS.md) for full setup instructions.

### SearXNG MCP

A bridge addon that connects Home Assistant's AI assistant to a self-hosted
[SearXNG](https://searxng.github.io/searxng/) instance.
Exposes `search` (web) and `search_news` tools over MCP SSE,
returning results as plain spoken English — no markdown, no symbols.

Requires a running SearXNG instance with the JSON format enabled and
the Home Assistant host IP whitelisted in SearXNG's limiter config.

See [searxng_mcp/DOCS.md](searxng_mcp/DOCS.md) for full setup instructions.

---

## Installation

In Home Assistant go to:
**Settings → Add-ons → Add-on Store → ⋮ → Repositories**

Add this URL:
```
https://github.com/MorningstarOwl/ha-addons
```
