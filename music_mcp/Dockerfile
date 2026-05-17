FROM python:3.12-slim

RUN pip install --no-cache-dir "mcp[cli]" httpx

COPY server.py /server.py

CMD ["python3", "/server.py"]
