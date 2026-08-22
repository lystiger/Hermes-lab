import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from fastapi import FastAPI, Request, Query, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from event_bus import event_bus, RuntimeEvent
from agent_service import agent_service
from agent_state_reducer import agent_state_reducer
from job_service import job_service
from job_state_reducer import job_state_reducer
from job_launcher import job_launcher
from normalization import normalize_agent_id


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
# Pydantic Schemas for Internal Event Ingress
# -------------------------------------------------------------

class EventSourcePayload(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    kind: Literal["agent", "system", "runtime", "tool"] = "agent"
    displayName: Optional[str] = None
    accentColor: Optional[str] = None


class InternalEventPayload(BaseModel):
    source: EventSourcePayload
    kind: str = Field(..., min_length=1, max_length=100)
    detail: str = Field(..., min_length=1, max_length=1000)
    duration: Optional[str] = "—"
    jobId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------
# Internal Ingress Endpoint (Cross-Process Runner -> Control Plane)
# -------------------------------------------------------------

@app.post("/internal/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_internal_event(payload: InternalEventPayload):
    """
    Ingests runtime execution telemetry events from Hermes sprint runners or external tools.
    Updates agent state reducer, job state reducer, and broadcasts to the canonical RuntimeEventBus.
    """
    raw_source_id = payload.source.id
    normalized_id = normalize_agent_id(raw_source_id)
    display_name = payload.source.displayName or normalized_id.capitalize()

    # 1. Update active agent state reducer
    agent_state_reducer.apply(
        source_id=normalized_id,
        kind=payload.kind,
        detail=payload.detail,
        metadata=payload.metadata,
    )

    # 2. Update active job state reducer (Phase 4)
    job_state_reducer.apply(
        kind=payload.kind,
        detail=payload.detail,
        job_id=payload.jobId,
        source_id=normalized_id,
        duration=payload.duration,
        metadata=payload.metadata,
    )

    # 3. Publish to the canonical RuntimeEventBus
    event = event_bus.publish(
        source_id=normalized_id,
        source_kind=payload.source.kind,
        source_name=display_name,
        kind=payload.kind,
        detail=payload.detail,
        duration=payload.duration or "—",
        job_id=payload.jobId,
        metadata=payload.metadata,
        accent_color=payload.source.accentColor,
    )

    return {
        "accepted": True,
        "eventId": event.id,
        "normalizedSourceId": normalized_id,
        "jobId": payload.jobId,
    }


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
    Returns dynamically registered agents from the runtime registry with real runtime status.
    """
    return agent_service.get_all_agents()


# -------------------------------------------------------------
# Real Job & Queue Endpoints (Phase 4)
# -------------------------------------------------------------

@app.get("/jobs")
async def get_jobs(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    Returns real sprint execution jobs tracked by the control plane.
    """
    return job_service.list_jobs(status=status_filter, limit=limit)


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """
    Returns detailed runtime execution state for a specific job.
    """
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return job.to_dict()


class CreateJobPayload(BaseModel):
    sprintId: str = Field(..., min_length=1, max_length=100)
    dryRun: bool = False
    skipAgentExec: bool = False


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: CreateJobPayload):
    """
    Safely triggers execution of a registered Hermes sprint definition.
    Rejects unknown sprint IDs or arbitrary command injection.
    """
    try:
        result = job_launcher.launch(
            sprint_id=payload.sprintId,
            dry_run=payload.dryRun,
            skip_agent_exec=payload.skipAgentExec,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cleanly cancels an active job runner process.
    """
    success = job_launcher.cancel(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active job '{job_id}' not found or not cancellable",
        )
    return {"cancelled": True, "jobId": job_id}


# -------------------------------------------------------------
# Runtime Event Bus Endpoints
# -------------------------------------------------------------

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
    Supports reconnect cursor via Last-Event-ID header (precedence) or ?after=<id>.
    """
    cursor_id = last_event_id or after
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
