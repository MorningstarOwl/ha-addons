# Web Search MCP

An MCP search addon for Home Assistant. Bundles a privacy-respecting
SearXNG metasearch instance and exposes web and news search as plain
spoken English over SSE — ideal for Assist and TTS pipelines. No
external server, no API keys, no configuration required.

---

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   Paste: `https://github.com/MorningstarOwl/ha-addons`

2. Install **Web Search MCP** from the store.

3. Optionally adjust settings in the **Configuration** tab (defaults work out of the box).

4. Start the addon.

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_results` | `5` | Number of results to include in each response (1–10). |
| `safe_search` | `0` | Safe search level: `0` = off, `1` = moderate, `2` = strict. |
| `language` | `all` | Result language code, e.g. `en-US`, `de`, `all`. |
| `engines` | `""` | Comma-separated list of SearXNG engines to query (e.g. `google,bing,wikipedia`). Leave empty to use SearXNG defaults for the category. |

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

**Prompt:** "Search for the latest news on renewable energy"

> Here are the top results for 'latest news on renewable energy'.
> Result 1: Global Renewable Energy Capacity Hits Record High. Wind and solar
> installations surpassed all previous records in the past year, according to
> the International Energy Agency.
> Result 2: New Battery Technology Could Transform Energy Storage. Researchers
> have developed a lithium-free battery that charges in under ten minutes.

---

## How It Works

The container runs two processes:

- **SearXNG** (granian) on `127.0.0.1:8080` — bundled, only reachable inside the container.
- **MCP wrapper** (Python / FastMCP) on `0.0.0.0:8766/sse` — what HA connects to.

Each search tool call hits the local SearXNG JSON API, takes the top results,
and formats them as spoken English. SearXNG's rate limiter is disabled inside
the addon because the only client is our local wrapper — there's no public
exposure to abuse.

The bundled SearXNG inherits the official upstream image, so engines and
security fixes track upstream automatically when the addon is rebuilt.

---

## Troubleshooting

### Searches return "temporarily unavailable"

Check the addon log tab. Most likely the bundled SearXNG didn't come up
within 60 seconds, or one of the configured engines is throwing errors.
Restart the addon to retry. If the issue persists, try setting
`engines: ""` to fall back to SearXNG defaults — a single misconfigured
engine can break a category.

### Searches return no results

Some queries genuinely return nothing. Try rephrasing. If you're seeing
zero results across many queries, the configured `language` may be
filtering too aggressively — try `language: all`.

### The addon won't start

Check the addon log tab for Python or granian errors. The most common
cause is port 8766 already being in use by another addon.

### Picking specific engines

The `engines` option takes a comma-separated list of SearXNG engine names.
Common picks for general search: `google,bing,duckduckgo,wikipedia`. For
news: `google news,bing news,reuters`. Browse the full list at the
SearXNG project: https://docs.searxng.org/admin/settings/settings_engine.html
