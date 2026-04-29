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

A privacy-respecting MCP search addon. Bundles a SearXNG metasearch instance
inside the container and exposes web and news search as plain spoken English
over SSE — no API keys, no external services, no rate-limit games. Drop it
in, point Home Assistant at the SSE endpoint, and Assist can search the web.

See [web_search_mcp/DOCS.md](web_search_mcp/DOCS.md) for full setup instructions.

### Memory MCP

A persistent, semantically searchable long-term memory for Home Assistant's
AI assistants. Stores preferences, facts, people, and routines, and recalls
them by meaning across restarts and updates. Fully self-contained —
embeddings run locally inside the addon using ChromaDB's bundled
`all-MiniLM-L6-v2` model. No Ollama, no API keys, no external services.

See [memory_mcp/DOCS.md](memory_mcp/DOCS.md) for full setup instructions.

---

## Installation

In Home Assistant go to:
**Settings → Add-ons → Add-on Store → ⋮ → Repositories**

Add this URL:
```
https://github.com/MorningstarOwl/ha-addons
```
