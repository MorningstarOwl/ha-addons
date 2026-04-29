#!/bin/sh
# Web Search MCP — container supervisor
# Brings up the bundled SearXNG instance on 127.0.0.1:8080, waits for it to
# pass /healthz, then execs the MCP SSE server on 0.0.0.0:8766.
#
# Design notes:
#   - We pin GRANIAN_HOST=127.0.0.1 so SearXNG only accepts traffic from
#     the local MCP wrapper. This matters because we disable SearXNG's
#     limiter / bot-detection — we don't want the JSON API reachable from
#     anywhere else inside the container's network namespace.
#   - The upstream entrypoint at /usr/local/searxng/entrypoint.sh handles
#     ownership fixups, settings.yml creation from our template, secret
#     substitution, and ca-cert refresh — we just delegate to it.
#   - If the MCP server exits, we kill SearXNG so the container exits and
#     HA Supervisor restarts the whole addon cleanly.

set -eu

export GRANIAN_HOST="127.0.0.1"
export GRANIAN_PORT="8080"

echo "[mcp] Starting bundled SearXNG (granian on ${GRANIAN_HOST}:${GRANIAN_PORT})..."
/usr/local/searxng/entrypoint.sh &
SEARXNG_PID=$!

echo "[mcp] Waiting for SearXNG to become healthy..."
ready=0
for i in $(seq 1 60); do
    if wget -qO- "http://127.0.0.1:${GRANIAN_PORT}/healthz" >/dev/null 2>&1; then
        echo "[mcp] SearXNG is up after ${i}s."
        ready=1
        break
    fi
    if ! kill -0 "$SEARXNG_PID" 2>/dev/null; then
        echo "[mcp] SearXNG exited during startup, aborting."
        exit 1
    fi
    sleep 1
done

if [ "$ready" -ne 1 ]; then
    echo "[mcp] SearXNG never became healthy within 60s, aborting."
    kill "$SEARXNG_PID" 2>/dev/null || true
    exit 1
fi

# If the MCP server exits for any reason, take SearXNG with us so HA
# Supervisor sees a clean exit and restarts the whole addon.
trap 'kill $SEARXNG_PID 2>/dev/null || true' EXIT INT TERM

echo "[mcp] Starting MCP SSE server on port 8766..."
exec /opt/mcp/bin/python3 /opt/mcp/server.py
