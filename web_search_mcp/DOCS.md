# Web Search MCP

An MCP search addon for Home Assistant. Uses DuckDuckGo to deliver web and
news search as spoken English — no external server, no configuration required.
Exposes two tools — `search` (web) and `search_news` — over SSE, ideal for
Assist and TTS pipelines.

---

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   Paste: `https://github.com/MorningstarOwl/ha-addons`

2. Install **Web Search MCP** from the store.

3. Start the addon. No configuration required — it works out of the box.

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_results` | `5` | Number of results to include in each response (1–10). |
| `safe_search` | `0` | Safe search level: `0` = off, `1` = moderate, `2` = strict. |

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
| `search_news` | News search |

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

### Searches return "temporarily unavailable"

DuckDuckGo occasionally rate-limits requests. Wait a moment and try again.
If it persists, check the addon log tab for details.

### The addon won't start

Check the addon log tab for Python errors.
