# MorningstarOwl HA Addons

Custom Home Assistant addon repository.

## Addons

### Weather MCP

A voice-friendly MCP server for Home Assistant's AI assistant integration.
Uses OpenWeatherMap to deliver current conditions and a 3-day forecast as
plain spoken English — no markdown, no symbols.

Location is read automatically from Home Assistant. If that fails, you can
set a **zip code** (e.g. `10001`) in the addon Configuration tab as a fallback.
City/state strings are not reliably supported by the OpenWeatherMap geocoding API.

See [weather_mcp/DOCS.md](weather_mcp/DOCS.md) for full setup instructions.

### Web Search MCP

An MCP search addon that uses DuckDuckGo to deliver web and news search
as plain spoken English — no markdown, no symbols, no external dependencies.

See [web_search_mcp/DOCS.md](web_search_mcp/DOCS.md) for full setup instructions.

---

## Installation

In Home Assistant go to:
**Settings → Add-ons → Add-on Store → ⋮ → Repositories**

Add this URL:
```
https://github.com/MorningstarOwl/ha-addons
```
