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

from events.event_bus import event_bus, RuntimeEvent
from personas.agent_service import agent_service
from personas.agent_state_reducer import agent_state_reducer
from jobs.job_service import job_service
from jobs.job_state_reducer import job_state_reducer
from jobs.job_launcher import job_launcher
from capabilities.normalization import normalize_agent_id
from artifacts.artifact_registry import ArtifactRef, artifact_registry
from messaging.message_store import message_store
from messaging.message_router import message_router
from runtime.storage.config import init_storage_lifespan, get_global_event_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize and validate storage connectivity (fails fast if configured DB is down)
    store = await init_storage_lifespan()
    job_service.set_store(store)

    # Recover historical messages from runs
    try:
        message_store.recover_from_runs(job_service.runs_root)
    except Exception as exc:
        pass

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
    await store.close()
    from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
    if isinstance(store, InMemoryRuntimeEventStore):
        store._closed = False


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
    kind: Literal["agent", "system", "runtime", "tool", "operator"] = "agent"
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
    normalized_id = normalize_agent_id(raw_source_id) if payload.source.kind == "agent" else raw_source_id
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


class InternalThreadPayload(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    jobId: Optional[str] = None
    title: Optional[str] = None
    participants: Optional[List[Dict[str, Any]]] = None


@app.post("/internal/threads", status_code=status.HTTP_202_ACCEPTED)
async def ingest_internal_thread(payload: InternalThreadPayload):
    thread = message_router.create_thread(
        thread_id=payload.id,
        job_id=payload.jobId,
        title=payload.title,
        participants=payload.participants,
    )
    return {"accepted": True, "threadId": thread.id}


class InternalMessagePayload(BaseModel):
    threadId: str = Field(..., min_length=1, max_length=100)
    from_actor: Dict[str, Any] = Field(..., alias="from")
    to_actors: List[Dict[str, Any]] = Field(default_factory=list, alias="to")
    kind: str = Field(..., min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=5000)
    intent: Optional[str] = None
    conversationId: Optional[str] = None
    replyTo: Optional[str] = None
    correlationId: Optional[str] = None
    jobId: Optional[str] = None
    phaseId: Optional[str] = None
    artifactRefs: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


@app.post("/internal/messages", status_code=status.HTTP_202_ACCEPTED)
async def ingest_internal_message(payload: InternalMessagePayload):
    msg = message_router.send_message(
        thread_id=payload.threadId,
        from_actor=payload.from_actor,
        to_actors=payload.to_actors,
        kind=payload.kind,
        text=payload.text,
        intent=payload.intent,
        conversation_id=payload.conversationId,
        reply_to=payload.replyTo,
        correlation_id=payload.correlationId,
        job_id=payload.jobId,
        phase_id=payload.phaseId,
        artifact_refs=payload.artifactRefs,
        metadata=payload.metadata,
    )
    return {"accepted": True, "messageId": msg.id}


class InternalArtifactPayload(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    ref: str = Field(..., min_length=1, max_length=500)
    jobId: Optional[str] = None
    phaseId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@app.post("/internal/artifacts", status_code=status.HTTP_202_ACCEPTED)
async def ingest_internal_artifact(payload: InternalArtifactPayload):
    artifact = ArtifactRef.from_dict(payload.model_dump())
    artifact_registry.register(artifact)
    return {"accepted": True, "artifactId": artifact.id}


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
    job = await job_service.get_job_async(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return job.to_dict()


@app.get("/jobs/{job_id}/tasks")
async def get_job_tasks(job_id: str):
    """
    Returns the reactive task dependency graph nodes for a specific job.
    """
    job = await job_service.get_job_async(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return await job_service.get_job_tasks_async(job_id)


@app.get("/jobs/{job_id}/runs")
async def get_job_runs(job_id: str):
    """
    Returns all actor execution run records for a specific job.
    """
    job = await job_service.get_job_async(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return await job_service.get_job_runs_async(job_id)


@app.get("/jobs/{job_id}/observations")
async def get_job_observations(job_id: str):
    """
    Returns all runtime observations discovered during job execution.
    """
    job = await job_service.get_job_async(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return await job_service.get_job_observations_async(job_id)


@app.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, limit: int = Query(default=100, ge=1, le=500)):
    """
    Returns historical runtime events scoped to a specific job from durable event store.
    """
    job = await job_service.get_job_async(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    store = get_global_event_store()
    stored_events = await store.list_events(job_id, limit=limit)
    if stored_events:
        return [e.to_dict() for e in stored_events]
    events = [e for e in event_bus.recent(limit=limit) if e.job_id == job_id]
    return [e.to_dict() for e in events]


class CreateJobPayload(BaseModel):
    sprintId: str = Field(..., min_length=1, max_length=100)
    dryRun: bool = False
    skipAgentExec: bool = False
    mode: Optional[str] = "reactive_runtime"


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: CreateJobPayload):
    """
    Safely triggers execution of a registered Hermes sprint definition.
    Persists initial job state before acknowledging creation.
    """
    try:
        result = await job_launcher.launch_async(
            sprint_id=payload.sprintId,
            dry_run=payload.dryRun,
            skip_agent_exec=payload.skipAgentExec,
            mode=payload.mode or "reactive_runtime",
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
    Cleanly and durably cancels an active job across event loops and processes.
    """
    success = await job_launcher.cancel_async(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active job '{job_id}' not found or not cancellable",
        )
    return {"cancelled": True, "jobId": job_id}


@app.get("/jobs/recoverable")
async def get_recoverable_jobs(limit: int = Query(default=50, ge=1, le=100)):
    """
    Discovers unfinished jobs from the canonical event ledger eligible for recovery.
    """
    store = get_global_event_store()
    unfinished_job_ids = await store.list_unfinished_jobs(limit=limit)
    recoverable = []
    for jid in unfinished_job_ids:
        job = await job_service.get_job_async(jid)
        if job and job.status not in ("COMPLETED", "CANCELLED"):
            recoverable.append(job.to_summary_dict())
    return recoverable


@app.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """
    Recovers and resumes an unfinished job from the canonical event store with lease exclusivity.
    """
    try:
        result = await job_launcher.resume_async(job_id)
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recovery failed: {exc}",
        )


@app.get("/jobs/{job_id}/recovery")
async def get_job_recovery_status(job_id: str):
    """
    Returns recovery status and measured RTO telemetry for a recovered job.
    """
    store = get_global_event_store()
    events = await store.list_events(job_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found in event store",
        )
    recovery_events = [e.to_dict() for e in events if e.event_type.startswith("recovery.")]
    return {
        "jobId": job_id,
        "recoveryCount": len([e for e in events if e.event_type == "recovery.completed"]),
        "events": recovery_events,
    }


# -------------------------------------------------------------
# Operational Messaging, Threads, Mailbox & Artifacts (Phase 5)
# -------------------------------------------------------------

@app.get("/threads")
async def get_threads(
    job_id: Optional[str] = Query(default=None, alias="jobId"),
    participant: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    Returns operational threads optionally filtered by jobId or participant.
    """
    threads = message_router.list_threads(job_id=job_id, participant=participant, limit=limit)
    return [t.to_dict() for t in threads]


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """
    Returns thread metadata for a specific operational thread.
    """
    thread = message_router.get_thread(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )
    return thread.to_dict()


@app.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    after: Optional[str] = Query(default=None),
    conversation_id: Optional[str] = Query(default=None, alias="conversationId"),
):
    """
    Returns messages belonging to a specific operational thread in chronological order.
    """
    messages = message_router.list_messages(thread_id=thread_id, limit=limit, after_id=after, conversation_id=conversation_id)
    return [m.to_dict() for m in messages]


class SendOperatorMessagePayload(BaseModel):
    threadId: str = Field(..., min_length=1, max_length=100)
    to: Optional[List[str]] = None
    kind: str = Field(default="operator", min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=2000)
    intent: Optional[str] = None
    conversationId: Optional[str] = None
    replyTo: Optional[str] = None
    correlationId: Optional[str] = None


@app.post("/messages", status_code=status.HTTP_201_CREATED)
async def send_operator_message(payload: SendOperatorMessagePayload):
    """
    Records and delivers an operator message into an existing thread.
    Does NOT execute arbitrary shell commands or trigger autonomous loops.
    """
    from_actor = {"id": "operator", "kind": "operator", "displayName": "Operator"}
    to_actors = payload.to or ["lysstack"]

    msg = message_router.send_message(
        thread_id=payload.threadId,
        from_actor=from_actor,
        to_actors=to_actors,
        kind=payload.kind,
        text=payload.text,
        intent=payload.intent,
        conversation_id=payload.conversationId,
        reply_to=payload.replyTo,
        correlation_id=payload.correlationId,
    )
    return msg.to_dict()


@app.get("/agents/{agent_id}/inbox")
async def get_agent_inbox(
    agent_id: str,
    state: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    job_id: Optional[str] = Query(default=None, alias="jobId"),
    thread_id: Optional[str] = Query(default=None, alias="threadId"),
    chronological: bool = Query(default=False),
    conversation_id: Optional[str] = Query(default=None, alias="conversationId"),
):
    """
    Returns mailbox entries targeted to the given agent with optional job/thread scoping.
    """
    entries = message_router.list_inbox(
        recipient_id=agent_id,
        state=state,
        limit=limit,
        job_id=job_id,
        thread_id=thread_id,
        chronological=chronological,
        conversation_id=conversation_id,
    )
    return [e.to_dict() for e in entries]


@app.post("/agents/{agent_id}/inbox/{message_id}/ack")
async def acknowledge_inbox_message(agent_id: str, message_id: str):
    """
    Acknowledges consumption of a mailbox message by the intended agent runtime.
    """
    success = message_router.acknowledge(message_id=message_id, recipient_id=agent_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found in {agent_id}'s inbox",
        )
    return {"acknowledged": True, "messageId": message_id, "recipientId": agent_id}


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
