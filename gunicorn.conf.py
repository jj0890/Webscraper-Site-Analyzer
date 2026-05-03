# Gunicorn configuration for Web Intelligence Dashboard
# Used by: ./start.sh production

# Server socket
bind = "127.0.0.1:8080"

# Workers — 2 is right for a CPU-bound scraping workload.
# More workers = more parallel scans but more memory per worker.
workers = 2

# Threads per worker — allows concurrent requests within a worker
# without spawning full processes. Useful for the dashboard UI
# serving static responses while a scan runs.
threads = 4

# Timeout — deep scans can take 2-3 minutes on heavy sites.
# 300s (5 min) covers all realistic cases.
timeout = 300

# Keep-alive — how long to hold an idle connection
keepalive = 5

# Logging
loglevel = "info"
accesslog = "-"   # stdout
errorlog = "-"    # stdout

# Graceful shutdown
graceful_timeout = 30

# Worker class — sync is correct here. We use asyncio internally
# (run_async wraps the event loop) so gevent/uvicorn aren't needed.
worker_class = "sync"
