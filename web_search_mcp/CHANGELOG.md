# Changelog

## 1.3.0 — Bundled SearXNG (take 2)

- Replaced the `duckduckgo-search` library with a bundled SearXNG instance.
  DuckDuckGo's anti-scraping protection rate-limits the library after the
  first request from a given IP, which surfaced as intermittent
  "temporarily unavailable" errors in 1.2.0.
- The container now runs SearXNG on `127.0.0.1:8080` internally; the MCP
  wrapper queries it locally over the JSON API. The bundled SearXNG has
  its limiter / bot-detection disabled — it's reachable only from the
  MCP wrapper inside the container.
- Re-added `language` and `engines` configuration options.
- Dropped `armhf` and `i386` architecture support — the upstream SearXNG
  image does not publish manifests for those arches.
- Inherits the official `searxng/searxng:latest` image so we get upstream
  security and engine updates automatically.

## 1.2.0 — Switch to DuckDuckGo (deprecated by 1.3.0)

- Replaced bundled SearXNG with the `duckduckgo-search` library
- No external server, no build dependencies, no startup process management
- Removed `searxng_url` and `language` configuration options
- Renamed addon to "Web Search MCP"
- Dockerfile reduced to 4 lines

## 1.1.0 — Bundled SearXNG (yanked)

- Attempted to bundle SearXNG inside the container
- Removed in favour of 1.2.0 due to build complexity

## 1.0.0 — Initial release

- `search` tool: general web search via SearXNG JSON API
- `search_news` tool: news category search
- Spoken-English result formatting with configurable result count
- Configurable safe search level and language
