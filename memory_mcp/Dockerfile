FROM python:3.12-slim

# Disable ChromaDB's anonymous telemetry — no outbound network calls at runtime.
ENV ANONYMIZED_TELEMETRY=False

# onnxruntime (pulled in transitively by chromadb) wants OpenMP at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# mcp is pinned below 2.x on purpose. The MCP Python SDK 2.0 renamed FastMCP to
# mcp.server.mcpserver.MCPServer and turned mcp.server.fastmcp into a stub that
# raises ModuleNotFoundError, so `from mcp.server.fastmcp import FastMCP` in
# server.py fails at import on 2.x. This dependency used to be unpinned, which
# meant the next rebuild -- and a version bump forces a rebuild -- would have
# resolved mcp to 2.x and produced an add-on that crashed before it could serve.
# Migrating to the 2.x API is a separate job across every add-on in this repo.
#
# Pin ChromaDB to the 0.5.x line. Bump deliberately after testing.
RUN pip install --no-cache-dir "mcp[cli]>=1.9,<2" "chromadb>=0.5.0,<0.6.0"

# Pre-bake the ONNX all-MiniLM-L6-v2 model into the image so the addon
# starts fully offline on first run. Spinning up an ephemeral in-memory
# client and adding one document triggers the default embedding function,
# which downloads and caches the ~90 MB ONNX model into the image layer.
RUN python -c "import chromadb; \
c = chromadb.Client(); \
col = c.get_or_create_collection('warmup'); \
col.add(documents=['warmup'], ids=['x'])"

COPY server.py /server.py

CMD ["python3", "/server.py"]
