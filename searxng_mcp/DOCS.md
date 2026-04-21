# SearXNG MCP

An all-in-one MCP search addon for Home Assistant. Bundles SearXNG internally —
no external search server required. Exposes two MCP tools — `search` (web) and
`search_news` — over SSE, returning results as plain spoken English with no
markdown or symbols, making it ideal for Assist and TTS pipelines.

---

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   Paste: `https://github.com/MorningstarOwl/ha-addons`

2. Install **SearXNG MCP** from the store.

3. Go to the **Configuration** tab and adjust options if desired (defaults work out of the box).

4. Start the addon.

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_results` | `5` | Number of results to include in each response (1–10). |
| `safe_search` | `0` | Safe search level: `0` = off, `1` = moderate, `2` = strict. |
| `language` | `en` | Search language/locale. |

---

## Connecting to Home Assistant

Once the addon is running, add the MCP integration:

**Settings → Devices & Services → Add Integration → Model Context Protocol**

When prompted for the SSE Server URL enter:

```
http://homeassistant.local:8766/sse
```

Or use the HA host's LAN IP directly if mDNS isn't reliable on your network:

```
http://<your-ha-ip>:8766/sse
```

The integration exposes two tools your AI assistant can call:

| Tool | Description |
|------|-------------|
| `search` | General web search |
| `search_news` | News-category search |

---

## Example Output

**Prompt:** "Search for the best practices for Docker networking"

> Here are the top results for 'best practices for Docker networking'.
> Result 1: Docker Networking Overview. Docker provides several networking
> drivers including bridge, host, and overlay — each suited to different
> use cases.
> Result 2: Using Bridge Networks in Docker. The default bridge network
> works for most single-host container communication scenarios.

---

## Troubleshooting

### Searches return "still starting up"

The bundled SearXNG instance takes a few seconds to initialize on first start.
Wait a moment and try again. If it persists, check the addon log tab for errors.

### Searches succeed but return no results

SearXNG relies on upstream search engines (Google, Bing, DuckDuckGo, etc.).
If all engines are temporarily unreachable or rate-limiting requests, results
may be empty. Try again after a short wait.

### The addon won't start

Check the addon log tab for Python errors. On lower-powered hardware, the
bundled SearXNG instance may need a moment longer to initialize — this is
normal on first start after install.
