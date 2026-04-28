FROM python:3.12-slim

# Disable ChromaDB's anonymous telemetry — no outbound network calls at runtime.
ENV ANONYMIZED_TELEMETRY=False

# onnxruntime (pulled in transitively by chromadb) wants OpenMP at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Pin ChromaDB to the 0.5.x line. Bump deliberately after testing.
RUN pip install --no-cache-dir "mcp[cli]" "chromadb>=0.5.0,<0.6.0"

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
