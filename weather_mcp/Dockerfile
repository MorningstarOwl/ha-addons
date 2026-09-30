FROM python:3.12-slim

# mcp is pinned below 2.x on purpose. The MCP Python SDK 2.0 renamed FastMCP to
# mcp.server.mcpserver.MCPServer and turned mcp.server.fastmcp into a stub that
# raises ModuleNotFoundError, so `from mcp.server.fastmcp import FastMCP` in
# server.py fails at import on 2.x. This dependency used to be unpinned, which
# meant the next rebuild -- and a version bump forces a rebuild -- would have
# resolved mcp to 2.x and produced an add-on that crashed before it could serve.
# Migrating to the 2.x API is a separate job across every add-on in this repo.
RUN pip install --no-cache-dir "mcp[cli]>=1.9,<2" httpx

COPY server.py /server.py

CMD ["python3", "/server.py"]
