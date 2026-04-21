"""
SearXNG MCP Server
------------------
Bundles a local SearXNG instance and exposes web/news search as MCP tools
over SSE, returning plain spoken English suitable for TTS read-back.

MCP SSE endpoint: http://homeassistant.local:8766/sse
"""

import json
import logging
import os
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

OPTIONS_FILE = "/data/options.json"
PORT = 8766
SEARXNG_URL = "http://127.0.0.1:8080"


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
LANGUAGE: str = options.get("language", "en")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_search_url(query: str, categories: str = "general") -> str:
    params = {
        "q": query,
        "format": "json",
        "language": LANGUAGE,
        "safesearch": SAFE_SEARCH,
        "categories": categories,
    }
    return f"{SEARXNG_URL}/search?{urlencode(params)}"


def results_to_spoken(results: list[dict], query: str) -> str:
    """
    Convert SearXNG result objects into a concise spoken-English summary.
    Each result becomes one sentence: title + a trimmed snippet.
    """
    if not results:
        return f"I couldn't find any results for '{query}'."

    lines: list[str] = [f"Here are the top results for '{query}'."]

    for i, r in enumerate(results[:MAX_RESULTS], start=1):
        title = r.get("title", "").strip()
        content = r.get("content", "").strip()

        # Trim content to a single readable sentence (≤ 180 chars)
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

mcp = FastMCP("SearXNG MCP Server", host="0.0.0.0", port=PORT)


@mcp.tool()
def search(query: str) -> str:
    """
    Search the web using the bundled SearXNG instance and return results
    as a natural spoken-English summary, suitable for voice read-back.

    Args:
        query: The search query string.
    """
    log.info(f"Searching SearXNG for: {query!r}")

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(build_search_url(query))
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        log.error(f"SearXNG HTTP error {e.response.status_code}: {e}")
        return "Search is temporarily unavailable. Please try again in a moment."
    except httpx.ConnectError:
        log.error("Could not connect to bundled SearXNG")
        return "Search is temporarily unavailable. The search engine is still starting up — please try again in a moment."
    except Exception as e:
        log.error(f"SearXNG request failed: {e}")
        return "Search is temporarily unavailable. Please try again in a moment."

    results = data.get("results", [])
    log.info(f"Got {len(results)} results for {query!r}")
    return results_to_spoken(results, query)


@mcp.tool()
def search_news(query: str) -> str:
    """
    Search for recent news using the bundled SearXNG instance and return
    results as a natural spoken-English summary.

    Args:
        query: The news search query string.
    """
    log.info(f"Searching SearXNG news for: {query!r}")

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(build_search_url(query, categories="news"))
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        log.error(f"SearXNG HTTP error {e.response.status_code}: {e}")
        return "News search is temporarily unavailable. Please try again in a moment."
    except httpx.ConnectError:
        log.error("Could not connect to bundled SearXNG")
        return "News search is temporarily unavailable. The search engine is still starting up — please try again in a moment."
    except Exception as e:
        log.error(f"SearXNG news request failed: {e}")
        return "News search is temporarily unavailable. Please try again in a moment."

    results = data.get("results", [])
    log.info(f"Got {len(results)} news results for {query!r}")
    return results_to_spoken(results, query)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(f"Max results: {MAX_RESULTS} | Safe search: {SAFE_SEARCH} | Language: {LANGUAGE}")
    log.info(f"Starting SearXNG MCP SSE server on port {PORT}...")
    mcp.run(transport="sse")
