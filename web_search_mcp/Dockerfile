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
#
# mcp is pinned below 2.x on purpose. The MCP Python SDK 2.0 renamed FastMCP to
# mcp.server.mcpserver.MCPServer and turned mcp.server.fastmcp into a stub that
# raises ModuleNotFoundError, so `from mcp.server.fastmcp import FastMCP` in
# server.py fails at import on 2.x. This dependency used to be unpinned, which
# meant the next rebuild -- and a version bump forces a rebuild -- would have
# resolved mcp to 2.x and produced an add-on that crashed before it could serve.
# Migrating to the 2.x API is a separate job across every add-on in this repo.
RUN /usr/local/searxng/.venv/bin/python3 -m venv /opt/mcp \
    && /opt/mcp/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/mcp/bin/pip install --no-cache-dir "mcp[cli]>=1.9,<2" httpx

# Ship our settings overlay directly at the runtime path. The upstream
# entrypoint creates /etc/searxng/settings.yml from the package template
# only when the file doesn't exist, so by COPYing it pre-baked we keep
# the upstream defaults file (/usr/local/searxng/searx/settings.yml)
# intact — that file is the SCHEMA SOURCE that `use_default_settings: true`
# reads at runtime, so replacing it breaks the merge and SearXNG fails to
# start with `Invalid settings.yml`. run.sh substitutes the placeholder
# secret_key on each container start.
COPY --chown=searxng:searxng rootfs/etc/searxng/settings.yml /etc/searxng/settings.yml

# MCP server + supervisor wrapper
COPY server.py /opt/mcp/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Override the upstream entrypoint with our wrapper that brings up SearXNG,
# waits for healthz, then runs the MCP server in the foreground.
ENTRYPOINT ["/run.sh"]
