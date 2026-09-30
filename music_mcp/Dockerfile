FROM python:3.12-slim

# mcp is pinned below 2.x on purpose. The MCP Python SDK 2.0 renamed FastMCP to
# mcp.server.mcpserver.MCPServer and deleted mcp.server.fastmcp; importing it on
# 2.x raises ModuleNotFoundError pointing at the migration guide. Since this
# dependency was previously unpinned, any rebuild after that release -- which a
# version bump forces -- produced an add-on that crashed before it could serve.
# Migrating to the 2.x API is a separate job across every add-on in this repo.
RUN pip install --no-cache-dir "mcp[cli]>=1.9,<2" "httpx>=0.27,<1"

COPY server.py /server.py

CMD ["python3", "/server.py"]
