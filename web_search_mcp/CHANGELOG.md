# Changelog

## 1.2.0 — Switch to DuckDuckGo

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
