FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "git+https://github.com/searxng/searxng.git" \
    "mcp[cli]" \
    httpx

RUN mkdir -p /etc/searxng
COPY settings.yml /etc/searxng/settings.yml

COPY server.py /server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

ENV SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml

CMD ["/run.sh"]
