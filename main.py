import threading
import time

from fastapi import FastAPI, Request

app = FastAPI()

_start_monotonic = time.monotonic()
_request_count = 0
_request_count_lock = threading.Lock()


@app.middleware("http")
async def count_requests(request: Request, call_next):
    global _request_count
    with _request_count_lock:
        _request_count += 1
    return await call_next(request)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/version")
def version():
    return {"version": "0.1.0"}


@app.get("/info")
def info():
    return {
        "name": "Hermes Lab",
        "version": "0.1.0",
        "environment": "development",
    }


@app.get("/metrics")
def metrics():
    with _request_count_lock:
        requests_handled = _request_count
    uptime_seconds = max(0, int(time.monotonic() - _start_monotonic))
    return {
        "uptime_seconds": uptime_seconds,
        "requests_handled": requests_handled,
    }
