import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from event_bus import event_bus, RuntimeEvent
from agent_service import agent_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Publish initial runtime startup event
    event_bus.publish(
        source_id="lysstack",
        source_kind="runtime",
        source_name="LysStack Control Plane",
        kind="runtime.started",
        detail="LysStack control-plane runtime initialized and listening on control bus",
        accent_color="#CBA35C",
    )
    yield
    # Publish stopping event on shutdown
    event_bus.publish(
        source_id="lysstack",
        source_kind="runtime",
        source_name="LysStack Control Plane",
        kind="runtime.stopping",
        detail="LysStack control-plane runtime shutting down",
        accent_color="#CBA35C",
    )


app = FastAPI(title="LysStack Control Plane", version="0.1.0", lifespan=lifespan)

# Allow local frontend origins
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_start_monotonic = time.monotonic()
_request_count = 0
_request_count_lock = threading.Lock()


@app.middleware("http")
async def count_requests(request: Request, call_next):
    global _request_count
    with _request_count_lock:
        _request_count += 1
    return await call_next(request)


# -------------------------------------------------------------
# Core LysStack Control API Endpoints
# -------------------------------------------------------------

@app.get("/health")
async def health_check():
    uptime = max(0, int(time.monotonic() - _start_monotonic))
    return {
        "status": "ok",
        "service": "lysstack",
        "version": "0.1.0",
        "uptimeSeconds": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/version")
async def version():
    return {"version": "0.1.0"}


@app.get("/info")
async def info():
    return {
        "name": "LysStack Control Plane",
        "version": "0.1.0",
        "environment": "development",
    }


@app.get("/metrics")
async def metrics():
    with _request_count_lock:
        requests_handled = _request_count
    uptime_seconds = max(0, int(time.monotonic() - _start_monotonic))
    return {
        "uptime_seconds": uptime_seconds,
        "requests_handled": requests_handled,
    }


@app.get("/agents")
async def get_agents():
    """
    Returns dynamically registered agents from the runtime registry.
    """
    return agent_service.get_all_agents()


@app.get("/events")
async def get_events(
    limit: int = Query(default=100, ge=1, le=500),
    after: Optional[str] = Query(default=None),
):
    """
    Retrieves recent historical runtime events from the event bus buffer.
    """
    events = event_bus.recent(limit=limit, after_id=after)
    return [e.to_dict() for e in events]


@app.get("/events/stream")
async def stream_events(
    request: Request,
    after: Optional[str] = Query(default=None),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    """
    Server-Sent Events (SSE) stream for real-time live runtime events.
    Supports reconnect cursor via ?after=<id> or Last-Event-ID header.
    """
    cursor_id = after or last_event_id
    queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue(maxsize=100)

    # Subscribe queue to live event bus
    event_bus.subscribe(queue)

    async def event_generator():
        try:
            # 1. Yield any missed historical events if a cursor was provided
            if cursor_id:
                historical = event_bus.recent(limit=100, after_id=cursor_id)
                for evt in historical:
                    yield f"id: {evt.id}\nevent: trace\ndata: {json.dumps(evt.to_dict())}\n\n"

            # 2. Stream live events with periodic heartbeat
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"id: {event.id}\nevent: trace\ndata: {json.dumps(event.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic SSE comment heartbeat to prevent socket timeouts
                    yield ": heartbeat\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
