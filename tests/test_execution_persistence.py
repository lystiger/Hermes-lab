"""The Execution page survives an API restart without showing resources that are gone."""

from datetime import datetime, timedelta, timezone

from runner.backends import events
from runner.backends.events import ExecutionEvent
from runner.backends.execution_registry import ExecutionRegistry, build_execution_snapshot


def ev(kind, rid="01AAAAAAAAAAAAAAAAAAAAAAAA", backend="openrig", **meta):
    return ExecutionEvent(kind=kind, job_id="j", detail="", task_id="T1", metadata={
        "backend": backend, "executionId": "e1",
        "resource": {"kind": "seat" if backend == "openrig" else "process", "id": rid, "label": "w"},
        "rigId": rid if backend == "openrig" else None, **meta,
    } if backend == "openrig" else {
        "backend": backend, "executionId": "e1", "resource": {"kind": "process", "id": rid, "label": "w"}, **meta,
    })


def restart(path):
    fresh = ExecutionRegistry()
    fresh.enable_persistence(path)
    return fresh


def test_rows_survive_a_restart_flagged_restored(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))

    [row] = restart(path).resources()
    assert row["state"] == "running" and row["taskId"] == "T1"
    assert row["details"]["restored"] is True


def test_released_rows_are_not_restored(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))
    reg.apply(ev(events.RESOURCE_RELEASED))
    assert restart(path).resources() == []


def test_a_live_event_clears_the_restored_flag(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))
    again = restart(path)
    again.apply(ev(events.RESOURCE_POOLED, expiresAt="2030-01-01T00:00:00Z"))
    [row] = again.resources()
    assert row["state"] == "idle" and "restored" not in row["details"] and "restoredAt" not in row


def test_restored_openrig_rows_whose_rig_is_gone_are_pruned(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING, rid="01AAAAAAAAAAAAAAAAAAAAAAAA"))
    reg.apply(ev(events.RUNNING, rid="01BBBBBBBBBBBBBBBBBBBBBBBB"))
    again = restart(path)

    again.prune_restored_rigs({"01BBBBBBBBBBBBBBBBBBBBBBBB"})

    assert [r["id"] for r in again.resources()] == ["01BBBBBBBBBBBBBBBBBBBBBBBB"]
    assert [r["id"] for r in restart(path).resources()] == ["01BBBBBBBBBBBBBBBBBBBBBBBB"]


def test_live_openrig_rows_are_never_pruned_by_the_rig_check(tmp_path):
    reg = ExecutionRegistry()
    reg.enable_persistence(tmp_path / "state.json")
    reg.apply(ev(events.RUNNING))
    reg.prune_restored_rigs(set())
    assert len(reg.resources()) == 1


def test_stale_restored_rows_expire(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING, backend="subprocess", rid="exec-1"))
    again = restart(path)
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    for row in again._resources.values():
        row["restoredAt"] = long_ago
    assert again.resources() == []


def test_a_corrupt_state_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert restart(path).resources() == []


def test_without_persistence_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reg = ExecutionRegistry()
    reg.apply(ev(events.RUNNING))
    assert list(tmp_path.iterdir()) == []


def test_snapshot_prunes_restored_rigs_only_when_the_daemon_answered(tmp_path, monkeypatch):
    from runner.backends import execution_registry as module

    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))
    again = restart(path)

    def probe(live_rig_ids=None, **kw):
        return [], {"daemon": "down", "ledger": {"owners": 0, "rigIds": []}}

    monkeypatch.setattr(module, "probe_backends", probe)
    assert len(build_execution_snapshot(registry=again)["resources"]) == 1  # daemon down: keep

    def probe_up(live_rig_ids=None, **kw):
        return [], {"daemon": "up", "ledger": {"owners": 0, "rigIds": []}}

    monkeypatch.setattr(module, "probe_backends", probe_up)
    assert build_execution_snapshot(registry=again)["resources"] == []  # daemon up, rig unknown: prune
