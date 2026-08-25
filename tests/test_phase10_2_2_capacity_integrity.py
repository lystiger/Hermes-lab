import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from runtime.capacity import (
    CapacityRegistry,
    ProviderStatus,
    ProviderFailureClass,
    UsageSnapshot,
    UsageSnapshotNormalizer,
    SoftCapacityThresholds,
    TaskBudgetEstimate,
)
from runtime.task_graph import TaskNode, TaskStatus
from runtime.scheduler import Scheduler, DispatchDecision
from runtime.hermes_adapter import HermesActorAdapter
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.observations import Observation, ObservationRegistry
from runtime.recovery import RecoveryManager, RecoveryMetrics
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.events import RuntimeEventBridge
from capabilities.capabilities import CapabilityRegistry
from runner.agents.claude import ClaudeAdapter
from runner.agents.antigravity import AntigravityAdapter
from runner.agents.codex import CodexAdapter
from runner.backends.base import ExecutionResult


def test_claude_style_json_to_usage_metadata():
    """
    Test 1: Claude JSON output is parsed into runtime_metadata with complete token usage.
    """
    claude_out = json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "model": "claude-3-5-sonnet-20241022",
        "usage": {
            "input_tokens": 2500,
            "output_tokens": 420,
            "cache_read_input_tokens": 800,
        },
        "content": [{"type": "text", "text": "All tasks completed successfully."}],
    })

    adapter = ClaudeAdapter()
    exec_res = ExecutionResult(
        command=("claude",),
        returncode=0,
        stdout=claude_out,
        stderr="",
        backend="cli",
    )

    adapter.validate_result(exec_res, context=None)
    assert hasattr(exec_res, "runtime_metadata")
    assert exec_res.runtime_metadata["usage"]["input_tokens"] == 2500
    assert exec_res.runtime_metadata["usage"]["output_tokens"] == 420
    assert exec_res.runtime_metadata["model"] == "claude-3-5-sonnet-20241022"

    # Normalize into UsageSnapshot
    snapshot = UsageSnapshotNormalizer.normalize(
        raw_data=exec_res.runtime_metadata,
        provider_id="anthropic",
        actor_id="claude",
    )
    assert snapshot.input_tokens == 2500
    assert snapshot.output_tokens == 420
    assert snapshot.source == "provider_reported"


def test_codex_supported_unsupported_truthful_unknown():
    """
    Test 2: Codex plain text output without usage metadata yields truthful UNKNOWN without invented limits.
    """
    adapter = CodexAdapter()
    exec_res = ExecutionResult(
        command=("codex",),
        returncode=0,
        stdout="Generated code patch in target directory.\nTests passed.",
        stderr="",
        backend="cli",
    )

    adapter.validate_result(exec_res, context=None)
    # Metadata is empty or absent
    meta = getattr(exec_res, "runtime_metadata", {}) or {}

    snapshot = UsageSnapshotNormalizer.normalize(
        raw_data=meta,
        provider_id="openai",
        actor_id="codex",
    )
    assert snapshot.source == "unknown"
    assert snapshot.tokens_remaining is None
    assert snapshot.requests_remaining is None
    assert snapshot.token_limit is None
    assert snapshot.request_limit is None


def test_antigravity_stream_json_usage_parsing():
    """
    Test 3: Antigravity stream-json output is parsed for usageMetadata across event lines.
    """
    event_1 = json.dumps({"event": "step", "message": "Analyzing repository..."})
    event_2 = json.dumps({"event": "tool", "tool_info": {"name": "read_file"}})
    event_3 = json.dumps({
        "event": "result",
        "status": "SUCCESS",
        "model": "gemini-2.0-flash",
        "usageMetadata": {
            "promptTokenCount": 3100,
            "candidatesTokenCount": 650,
            "cachedContentTokenCount": 1200,
        },
    })
    stdout_text = f"{event_1}\n{event_2}\n{event_3}"

    adapter = AntigravityAdapter()
    exec_res = ExecutionResult(
        command=("agy",),
        returncode=0,
        stdout=stdout_text,
        stderr="",
        backend="cli",
    )

    adapter.validate_result(exec_res, context=None)
    assert hasattr(exec_res, "runtime_metadata")
    assert exec_res.runtime_metadata["usage"]["promptTokenCount"] == 3100
    assert exec_res.runtime_metadata["usage"]["candidatesTokenCount"] == 650
    assert exec_res.runtime_metadata["usage"]["cachedContentTokenCount"] == 1200

    snapshot = UsageSnapshotNormalizer.normalize(
        raw_data=exec_res.runtime_metadata,
        provider_id="google",
        actor_id="antigravity",
    )
    assert snapshot.input_tokens == 3100
    assert snapshot.output_tokens == 650
    assert snapshot.cached_tokens == 1200
    assert snapshot.source == "provider_reported"


def test_registry_preserves_remaining_quota_on_usage_record():
    """
    Test 4: Registry record_snapshot and record_usage preserve remaining quota fields
    when incremental token calls do not carry new headers.
    """
    registry = CapacityRegistry()
    registry.register_actor_provider("claude_actor", "anthropic")

    # Initial snapshot with observable remaining quota headers
    initial_snap = UsageSnapshot(
        provider_id="anthropic",
        actor_id="claude_actor",
        input_tokens=1000,
        output_tokens=200,
        tokens_remaining=45000,
        token_limit=50000,
        requests_remaining=480,
        request_limit=500,
        context_window=200000,
        context_used=1200,
        reset_at="2026-08-25T17:00:00Z",
        source="provider_reported",
    )
    registry.record_snapshot(initial_snap, job_id="job_1")

    # Incremental token recording (e.g. from internal accounting without rate-limit headers)
    registry.record_usage(
        provider_id="anthropic",
        job_id="job_1",
        input_tokens=500,
        output_tokens=100,
    )

    persisted = registry.get_usage("anthropic")
    assert persisted is not None
    # Token totals aggregated
    assert persisted.input_tokens == 1500
    assert persisted.output_tokens == 300
    assert persisted.tokens_used == 1800
    # Capacity limit & remaining fields strictly PRESERVED
    assert persisted.tokens_remaining == 45000
    assert persisted.token_limit == 50000
    assert persisted.requests_remaining == 480
    assert persisted.request_limit == 500
    assert persisted.context_window == 200000
    assert persisted.reset_at == "2026-08-25T17:00:00Z"
    assert persisted.source == "provider_reported"


def test_unassigned_low_capacity_top_scorer_loses_to_healthy_candidate():
    """
    Test 5: An unassigned task matching multiple candidates chooses the healthy candidate
    even if the top-scoring candidate has degraded soft capacity (8% remaining tokens).
    """
    cap_reg = CapabilityRegistry()
    # Candidate 1: Senior builder (higher proficiency score)
    cap_reg.register_actor({
        "id": "senior_agent",
        "name": "Senior Agent",
        "capabilities": ["backend", "database", "python"],
    })
    # Candidate 2: Standard builder (satisfies requirements)
    cap_reg.register_actor({
        "id": "standard_agent",
        "name": "Standard Agent",
        "capabilities": ["backend", "database", "python"],
    })

    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("senior_agent", "provider_degraded")
    capacity_reg.register_actor_provider("standard_agent", "provider_healthy")

    # Senior agent provider has only 8% tokens remaining (degraded soft capacity)
    capacity_reg._usage_snapshots["provider_degraded"] = UsageSnapshot(
        provider_id="provider_degraded",
        tokens_remaining=8000,
        token_limit=100000,
        source="provider_reported",
    )

    # Standard agent provider is healthy (85% tokens remaining)
    capacity_reg._usage_snapshots["provider_healthy"] = UsageSnapshot(
        provider_id="provider_healthy",
        tokens_remaining=85000,
        token_limit=100000,
        source="provider_reported",
    )

    scheduler = Scheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
    )

    unassigned_task = TaskNode(
        task_id="T_UNASSIGNED",
        job_id="job_unassigned",
        description="Complex DB Migration",
        required_capabilities=["backend", "database"],
        assigned_actor=None,  # Pure capability match from candidate pool
    )

    decision = scheduler.match_actor_for_task(unassigned_task)
    assert decision.dispatched is True
    # The healthy candidate wins over the degraded top candidate
    assert decision.actor_id == "standard_agent"
    assert "senior_agent" in decision.rejected_candidates
    assert "Soft capacity degraded" in decision.rejected_candidates["senior_agent"]


@pytest.mark.anyio
async def test_context_handoff_survives_reconstruction():
    """
    Test 6: Continuity handoff observation emitted during execution is properly
    preserved in the event store and reconstructed by RuntimeStateProjector.
    """
    event_store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=event_store)

    job_id = "job_handoff_recon"
    t1 = TaskNode(task_id="T1", job_id=job_id, status=TaskStatus.SUCCEEDED, description="Heavy Task")

    from runtime.job_state import JobRecord, JobState
    job = JobRecord(job_id=job_id, goal="Handoff Reconstruction", state=JobState.EXECUTING)

    await bridge.emit_job_created(job)
    await bridge.emit_task_created(t1)

    # Emit continuity handoff observation
    handoff_obs = Observation(
        job_id=job_id,
        task_id="T1",
        actor_id="claude",
        kind="continuity_handoff",
        content="Context pressure handoff at 91.5% context window. Discovered schema v2 constraints.",
        metadata={"context_pressure": True, "fresh_session": True, "context_ratio": 0.915},
    )
    await bridge.emit_observation_created(handoff_obs)

    # Reconstruct from event store
    events = await event_store.list_events(job_id)
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)

    assert len(reconstructed.observations) == 1
    obs = reconstructed.observations[0]
    assert obs.kind == "continuity_handoff"
    assert "91.5%" in obs.content
    assert obs.metadata.get("fresh_session") is True
    assert obs.metadata.get("context_pressure") is True


@pytest.mark.anyio
async def test_true_rto_survives_reconstruction():
    """
    Test 7: recovery.execution_resumed emitted on task dispatch is projected
    and survives full store reconstruction.
    """
    event_store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=event_store)

    job_id = "job_rto_recon"
    t1 = TaskNode(task_id="T1", job_id=job_id, status=TaskStatus.READY, description="Task 1")

    from runtime.job_state import JobRecord, JobState
    job = JobRecord(job_id=job_id, goal="RTO Recon Test", state=JobState.EXECUTING)

    await bridge.emit_job_created(job)
    await bridge.emit_task_created(t1)

    interrupted_time = (datetime.now(timezone.utc) - timedelta(seconds=12)).isoformat()
    manager = RecoveryManager(event_store=event_store)
    engine, metrics = await manager.recover_and_rehydrate(
        job_id=job_id,
        detected_interruption_at=interrupted_time,
    )

    # Trigger scheduler task dispatch
    await engine.step()

    # Reconstruct from store
    events = await event_store.list_events(job_id)
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)

    # Assert recovery RTO metadata is authoritatively projected on JobRecord
    assert reconstructed.job.metadata.get("recovery_rto_seconds") is not None
    assert reconstructed.job.metadata["recovery_rto_seconds"] >= 12.0
    assert reconstructed.job.metadata.get("recovery_resumed_at") is not None


class ClaudeMockWithFullCapacityAgent:
    name = "claude"

    def build_command(self, prompt, options, worktree=None):
        return ["echo", "mock_claude"]

    def execute(self, context):
        claude_out = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "model": "claude-3-5-sonnet-20241022",
            "usage": {
                "input_tokens": 2500,
                "output_tokens": 420,
            },
            "tokens_remaining": 8000,
            "token_limit": 100000,
            "context_used": 90000,
            "context_window": 100000,
            "content": [{"type": "text", "text": "All tasks completed."}],
        })
        res = ExecutionResult(
            command=("claude",),
            returncode=0,
            stdout=claude_out,
            stderr="",
            backend="cli",
        )
        ClaudeAdapter().validate_result(res, context=None)
        return res


@pytest.mark.anyio
async def test_real_adapter_to_scheduler_canonical_snapshot_e2e(tmp_path: Path):
    """
    Test 8: Real Adapter -> Scheduler Canonical Snapshot Transfer E2E.
    Validates that raw provider output normalized in HermesActorAdapter flows
    into TaskExecutionResult and is deserialized directly by Scheduler into
    CapacityRegistry without double-writes or renormalization.
    """
    from runner.agents.registry import AgentRegistry
    from runtime.task_graph import TaskGraph
    from runtime.execution import ExecutionManager

    agent_reg = AgentRegistry()
    agent_reg.register(ClaudeMockWithFullCapacityAgent())

    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({
        "id": "claude",
        "name": "Claude Agent",
        "capabilities": ["backend", "python"],
    })

    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("claude", "anthropic")

    scheduler = Scheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
    )

    adapter = HermesActorAdapter(
        target_repo=tmp_path,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "runs",
        agent_registry=agent_reg,
        dry_run=False,
    )

    exec_manager = ExecutionManager()
    exec_manager.register_adapter("claude", adapter)

    graph = TaskGraph()
    task = TaskNode(
        task_id="T_CLAUDE_E2E",
        job_id="job_claude_e2e",
        description="Production E2E Task",
        assigned_actor="claude",
        status=TaskStatus.READY,
    )
    graph.add_task(task)

    # Schedule and execute task through real scheduler & execution manager
    async_tasks = await scheduler.schedule_ready_tasks(
        graph=graph,
        execution_manager=exec_manager,
        context={"job": {"job_id": "job_claude_e2e"}},
    )
    if async_tasks:
        await asyncio.gather(*async_tasks)

    # Verify task completed
    assert task.status == TaskStatus.SUCCEEDED

    # Verify CapacityRegistry state in scheduler
    usage = capacity_reg.get_usage("anthropic")
    assert usage is not None
    assert usage.input_tokens == 2500
    assert usage.output_tokens == 420
    assert usage.tokens_used == 2920

    assert usage.tokens_remaining == 8000
    assert usage.token_limit == 100000
    assert usage.context_used == 90000
    assert usage.context_window == 100000
    assert usage.source == "provider_reported"
