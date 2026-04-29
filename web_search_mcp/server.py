"""
Web Search MCP Server
---------------------
Reads options from /data/options.json (injected by HA Supervisor),
queries the bundled SearXNG instance on 127.0.0.1:8080, and returns
results as plain spoken English suitable for TTS read-back.

MCP SSE endpoint: http://homeassistant.local:8766/sse
"""

import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
PORT = 8766
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080")
REQUEST_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Load addon options
# ---------------------------------------------------------------------------

def load_options() -> dict:
    try:
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not read options.json: {e}")
        return {}


options = load_options()
MAX_RESULTS: int = int(options.get("max_results", 5))
SAFE_SEARCH: int = int(options.get("safe_search", 0))
LANGUAGE: str = (options.get("language") or "all").strip() or "all"
ENGINES: list[str] = [
    e.strip() for e in (options.get("engines") or "").split(",") if e.strip()
]


# ---------------------------------------------------------------------------
# SearXNG client
# ---------------------------------------------------------------------------

def _searxng_request(query: str, category: str = "general") -> list[dict]:
    """Hit the local SearXNG JSON API and return the `results` list."""
    params = {
        "q": query,
        "format": "json",
        "safesearch": SAFE_SEARCH,
        "language": LANGUAGE,
        "categories": category,
    }
    if ENGINES:
        params["engines"] = ",".join(ENGINES)

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        r = client.get(f"{SEARXNG_URL}/search", params=params)
        r.raise_for_status()
        return r.json().get("results", []) or []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def results_to_spoken(results: list[dict], query: str) -> str:
    """Convert SearXNG result dicts into a concise spoken-English summary."""
    if not results:
        return f"I couldn't find any results for '{query}'."

    lines: list[str] = [f"Here are the top results for '{query}'."]

    for i, r in enumerate(results[:MAX_RESULTS], start=1):
        title = (r.get("title") or "").strip()
        # SearXNG returns the snippet under "content" (DDG used "body")
        content = (r.get("content") or "").strip()

        if content:
            for sep in (".", "!", "?"):
                idx = content.find(sep)
                if 0 < idx <= 200:
                    content = content[: idx + 1]
                    break
            else:
                content = content[:180].rsplit(" ", 1)[0] + "…"
        else:
            content = "No description available."

        if title:
            lines.append(f"Result {i}: {title}. {content}")
        else:
            lines.append(f"Result {i}: {content}")

    return " ".join(lines)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Web Search MCP Server", host="0.0.0.0", port=PORT)


@mcp.tool()
def search(query: str) -> str:
    """
    Search the web via the bundled SearXNG instance and return results
    as a natural spoken-English summary, suitable for voice read-back.

    Args:
        query: The search query string.
    """
    log.info(f"Searching for: {query!r}")
    try:
        results = _searxng_request(query, category="general")
    except Exception as e:
        log.error(f"Search failed: {e}")
        return "Search is temporarily unavailable. Please try again in a moment."

    log.info(f"Got {len(results)} results for {query!r}")
    return results_to_spoken(results, query)


@mcp.tool()
def search_news(query: str) -> str:
    """
    Search recent news via the bundled SearXNG instance and return results
    as a natural spoken-English summary.

    Args:
        query: The news search query string.
    """
    log.info(f"Searching news for: {query!r}")
    try:
        results = _searxng_request(query, category="news")
    except Exception as e:
        log.error(f"News search failed: {e}")
        return "News search is temporarily unavailable. Please try again in a moment."

    log.info(f"Got {len(results)} news results for {query!r}")
    return results_to_spoken(results, query)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(
        f"SearXNG: {SEARXNG_URL} | max_results={MAX_RESULTS} "
        f"safesearch={SAFE_SEARCH} lang={LANGUAGE} "
        f"engines={','.join(ENGINES) if ENGINES else 'default'}"
    )
    log.info(f"Starting Web Search MCP SSE server on port {PORT}...")
    mcp.run(transport="sse")
