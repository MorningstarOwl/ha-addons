# Changelog

## 1.1.0 — Bundled SearXNG (no external dependencies)

- SearXNG is now bundled inside the addon container — no separate search server required
- Removed `searxng_url` configuration option
- Simplified DOCS: no SearXNG setup or whitelist steps needed

## 1.0.0 — Initial release

- `search` tool: general web search via SearXNG JSON API
- `search_news` tool: news category search
- Spoken-English result formatting with configurable result count
- Descriptive error messages for common failure modes (403, connection error)
- Configurable safe search level and language
