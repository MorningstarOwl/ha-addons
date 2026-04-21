"""
Web Search MCP Server
---------------------
Reads options from /data/options.json (injected by HA Supervisor),
queries DuckDuckGo for web search results, and returns them as plain
spoken English suitable for TTS read-back.

MCP SSE endpoint: http://homeassistant.local:8766/sse
"""

import json
import logging

from duckduckgo_search import DDGS
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
PORT = 8766

SAFE_SEARCH_MAP = {0: "off", 1: "moderate", 2: "on"}


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
SAFE_SEARCH: str = SAFE_SEARCH_MAP.get(int(options.get("safe_search", 0)), "off")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def results_to_spoken(results: list[dict], query: str) -> str:
    """Convert search result dicts into a concise spoken-English summary."""
    if not results:
        return f"I couldn't find any results for '{query}'."

    lines: list[str] = [f"Here are the top results for '{query}'."]

    for i, r in enumerate(results[:MAX_RESULTS], start=1):
        title = r.get("title", "").strip()
        content = r.get("body", "").strip()

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
    Search the web using DuckDuckGo and return results as a natural
    spoken-English summary, suitable for voice read-back.

    Args:
        query: The search query string.
    """
    log.info(f"Searching for: {query!r}")
    try:
        results = DDGS().text(query, max_results=MAX_RESULTS, safesearch=SAFE_SEARCH)
    except Exception as e:
        log.error(f"Search failed: {e}")
        return "Search is temporarily unavailable. Please try again in a moment."

    log.info(f"Got {len(results)} results for {query!r}")
    return results_to_spoken(results, query)


@mcp.tool()
def search_news(query: str) -> str:
    """
    Search for recent news using DuckDuckGo and return results as a
    natural spoken-English summary.

    Args:
        query: The news search query string.
    """
    log.info(f"Searching news for: {query!r}")
    try:
        results = DDGS().news(query, max_results=MAX_RESULTS, safesearch=SAFE_SEARCH)
    except Exception as e:
        log.error(f"News search failed: {e}")
        return "News search is temporarily unavailable. Please try again in a moment."

    log.info(f"Got {len(results)} news results for {query!r}")
    return results_to_spoken(results, query)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(f"Max results: {MAX_RESULTS} | Safe search: {SAFE_SEARCH}")
    log.info(f"Starting Web Search MCP SSE server on port {PORT}...")
    mcp.run(transport="sse")
