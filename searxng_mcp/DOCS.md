# SearXNG MCP

A bridge addon that connects Home Assistant's AI assistant to your
self-hosted [SearXNG](https://searxng.github.io/searxng/) instance.
It exposes two MCP tools — `search` (web) and `search_news` — over SSE,
returning results as plain spoken English with no markdown or symbols,
making it ideal for Assist and TTS pipelines.

---

## Prerequisites

- A running SearXNG instance accessible from the Home Assistant host.
- SearXNG must have the `json` output format enabled.
- The Home Assistant host IP must be whitelisted in SearXNG's rate-limiter
  config (see [SearXNG Configuration](#searxng-configuration) below).

---

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   Paste: `https://github.com/MorningstarOwl/ha-addons`

2. Install **SearXNG MCP** from the store.

3. Go to the **Configuration** tab and set your options (see below).

4. **Complete the SearXNG configuration steps** described in this document
   before starting the addon — if SearXNG isn't ready to accept requests from
   the HA host, the addon will start but all searches will return 403 errors.

5. Start the addon.

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `searxng_url` | `http://192.168.1.212:8888` | Full URL to your SearXNG instance. Change this to match your server's IP and port. |
| `max_results` | `5` | Number of results to include in each response (1–10). |
| `safe_search` | `0` | Safe search level: `0` = off, `1` = moderate, `2` = strict. |
| `language` | `en` | Search language/locale passed to SearXNG. |

---

## SearXNG Configuration

Two things must be true on the SearXNG side before this addon will work.
Both changes are made to files in your SearXNG stack's `./settings/` directory.

### 1. Enable JSON output format

Open `settings/settings.yml` and ensure `json` is listed under `search.formats`:

```yaml
search:
  formats:
    - html
    - json      # ← this line must be present
```

Restart the SearXNG container after saving.

### 2. Whitelist the Home Assistant host IP

SearXNG's built-in rate-limiter (`limiter.toml`) blocks requests from IPs
it doesn't recognize. The addon runs on the **Home Assistant OS host**, so
that IP must be explicitly allowed.

> **What IP is the HA host?**
> By default, Home Assistant OS is at `192.168.1.168` on this network.
> Check **Settings → System → Network** in HA if you're unsure.

Open `settings/limiter.toml`. Add the HA host IP (and optionally the HA
addon network subnet) to the allowed list. A minimal working example
that preserves Docker-internal access:

```toml
[botdetection.ip_limit]
# IPs in this list are never rate-limited or blocked
link_token = false

[botdetection.ip_lists]
pass_ip = [
    "127.0.0.1",          # localhost
    "172.16.0.0/12",      # Docker bridge subnets
    "192.168.1.0/24",     # Your full LAN — simplest option
]
```

If you prefer tighter control, replace `192.168.1.0/24` with just the
specific addresses that need access:

```toml
pass_ip = [
    "127.0.0.1",
    "172.16.0.0/12",
    "192.168.1.168",      # Home Assistant OS host
    "192.168.1.212",      # AI server (if you also use SearXNG from there)
]
```

Restart the SearXNG container after saving.

### Verify SearXNG is ready

From the Home Assistant host (or any whitelisted machine), test that the
JSON API responds correctly:

```bash
curl "http://192.168.1.212:8888/search?q=test&format=json" | head -c 200
```

You should see a JSON object starting with `{"query":`. If you get a `403`
or an HTML error page, the limiter config is not yet correct.

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
http://192.168.1.168:8766/sse
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

### All searches return "403 Forbidden"

The Home Assistant host IP is not whitelisted in SearXNG's `limiter.toml`.
Follow the [whitelist instructions](#2-whitelist-the-home-assistant-host-ip)
above and restart the SearXNG container.

### All searches return "Could not reach the SearXNG server"

- Confirm the `searxng_url` option is correct (right IP and port).
- Confirm SearXNG is running: open the URL in a browser from the HA host.
- If SearXNG is on a different subnet, ensure routing/firewall rules allow
  the connection.

### Searches succeed but return no results

- Confirm `json` is in `search.formats` in `settings.yml`.
- Try the curl test above to confirm the JSON API works independently of
  the addon.

### The addon won't start

Check the addon log tab for Python errors. The most common cause is a
malformed `searxng_url` (e.g. a trailing slash was accidentally added twice,
or the URL includes a path component).
