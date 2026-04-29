# syntax=docker/dockerfile:1
#
# Web Search MCP — Home Assistant addon (bundled SearXNG)
# -------------------------------------------------------
# Inherits the official multi-arch SearXNG image (amd64 / arm64 / armv7),
# layers a small Python MCP server on top, and ships a settings overlay
# that exposes the JSON API and disables the rate limiter.
#
# Inside the container, SearXNG listens on 127.0.0.1:8080 (granian) and the
# MCP wrapper listens on 0.0.0.0:8766 (SSE). Only the MCP port is exposed
# externally via the addon's `ports:` mapping.

FROM docker.io/searxng/searxng:latest

USER root

# Build an isolated venv for the MCP server using the Python that already
# ships in the SearXNG venv. Avoids depending on system Python in the
# minimal base image, and keeps our deps separate from SearXNG's deps.
RUN /usr/local/searxng/.venv/bin/python3 -m venv /opt/mcp \
    && /opt/mcp/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/mcp/bin/pip install --no-cache-dir "mcp[cli]" httpx

# Replace the default SearXNG settings template with our minimal overlay.
# The upstream entrypoint copies this file to $__SEARXNG_SETTINGS_PATH on
# first start and substitutes "ultrasecretkey" with a random per-container
# value via sed. Everything else falls through to upstream defaults.
COPY rootfs/usr/local/searxng/searx/settings.yml /usr/local/searxng/searx/settings.yml

# MCP server + supervisor wrapper
COPY server.py /opt/mcp/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Override the upstream entrypoint with our wrapper that brings up SearXNG,
# waits for healthz, then runs the MCP server in the foreground.
ENTRYPOINT ["/run.sh"]
