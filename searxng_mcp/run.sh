#!/bin/sh
set -e

# Start SearXNG in the background
python3 -m searx.webapp &

# Wait up to 30 seconds for SearXNG to accept connections
python3 -c "
import socket, time, sys
for _ in range(30):
    try:
        socket.create_connection(('127.0.0.1', 8080), 1).close()
        break
    except OSError:
        time.sleep(1)
else:
    print('SearXNG failed to start within 30 seconds', file=sys.stderr)
    sys.exit(1)
"

# Start MCP server in the foreground
exec python3 /server.py
