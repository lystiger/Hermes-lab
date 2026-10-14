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


def restart(path, previous=None):
    if previous is not None:
        previous.flush()  # saves are asynchronous: wait for the write before "restarting"
    fresh = ExecutionRegistry()
    fresh.enable_persistence(path)
    return fresh


def test_rows_survive_a_restart_flagged_restored(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))

    [row] = restart(path, reg).resources()
    assert row["state"] == "running" and row["taskId"] == "T1"
    assert row["details"]["restored"] is True


def test_released_rows_are_not_restored(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))
    reg.apply(ev(events.RESOURCE_RELEASED))
    assert restart(path, reg).resources() == []


def test_a_live_event_clears_the_restored_flag(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING))
    again = restart(path, reg)
    again.apply(ev(events.RESOURCE_POOLED, expiresAt="2030-01-01T00:00:00Z"))
    [row] = again.resources()
    assert row["state"] == "idle" and "restored" not in row["details"] and "restoredAt" not in row


def test_restored_openrig_rows_whose_rig_is_gone_are_pruned(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING, rid="01AAAAAAAAAAAAAAAAAAAAAAAA"))
    reg.apply(ev(events.RUNNING, rid="01BBBBBBBBBBBBBBBBBBBBBBBB"))
    again = restart(path, reg)

    again.prune_restored_rigs({"01BBBBBBBBBBBBBBBBBBBBBBBB"})

    assert [r["id"] for r in again.resources()] == ["01BBBBBBBBBBBBBBBBBBBBBBBB"]
    assert [r["id"] for r in restart(path, again).resources()] == ["01BBBBBBBBBBBBBBBBBBBBBBBB"]


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
    again = restart(path, reg)
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    for row in again._resources.values():
        row["restoredAt"] = long_ago
    assert again.resources() == []


def test_a_corrupt_state_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert restart(path, None).resources() == []


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
    again = restart(path, reg)

    def probe(live_rig_ids=None, **kw):
        return [], {"daemon": "down", "ledger": {"owners": 0, "rigIds": []}}

    monkeypatch.setattr(module, "probe_backends", probe)
    assert len(build_execution_snapshot(registry=again)["resources"]) == 1  # daemon down: keep

    def probe_up(live_rig_ids=None, **kw):
        return [], {"daemon": "up", "ledger": {"owners": 0, "rigIds": []}}

    monkeypatch.setattr(module, "probe_backends", probe_up)
    assert build_execution_snapshot(registry=again)["resources"] == []  # daemon up, rig unknown: prune


def test_apply_never_waits_for_a_slow_disk(tmp_path, monkeypatch):
    import time as _time

    reg = ExecutionRegistry()
    reg.enable_persistence(tmp_path / "state.json")
    reg.flush()
    real = reg._save_now
    monkeypatch.setattr(reg, "_save_now", lambda: (_time.sleep(0.3), real()))

    started = _time.monotonic()
    for _ in range(5):
        reg.apply(ev(events.RUNNING))
    assert _time.monotonic() - started < 0.1


def test_restart_never_renews_a_stale_row_and_expiry_is_saved(tmp_path):
    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.apply(ev(events.RUNNING, backend="subprocess", rid="exec-1"))
    first = restart(path, reg)
    first_restored = first.resources()[0]["restoredAt"]
    second = restart(path, first)
    assert second.resources()[0]["restoredAt"] == first_restored  # not renewed by the restart

    long_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    for row in second._resources.values():
        row["restoredAt"] = long_ago
    assert second.resources() == []
    assert restart(path, second).resources() == []  # the expiry was persisted


def test_flush_waits_for_a_write_already_in_progress(tmp_path, monkeypatch):
    import json as _json
    import threading as _threading
    import time as _time

    path = tmp_path / "state.json"
    reg = ExecutionRegistry()
    reg.enable_persistence(path)
    reg.flush()
    real = reg._save_now
    started = _threading.Event()

    def slow():
        started.set()
        _time.sleep(0.3)
        real()

    monkeypatch.setattr(reg, "_save_now", slow)
    reg.apply(ev(events.RUNNING))
    assert started.wait(2)  # the writer has taken the work: nothing is queued any more
    assert reg.flush(timeout=5) is True
    assert len(_json.loads(path.read_text())) == 1


def test_flush_gives_up_at_its_timeout(tmp_path, monkeypatch):
    import time as _time

    reg = ExecutionRegistry()
    reg.enable_persistence(tmp_path / "state.json")
    reg.flush()
    monkeypatch.setattr(reg, "_save_now", lambda: _time.sleep(1.0))
    reg.apply(ev(events.RUNNING))
    started = _time.monotonic()
    assert reg.flush(timeout=0.2) is False
    assert _time.monotonic() - started < 0.6


def test_the_test_session_never_points_at_real_user_state():
    import os
    from pathlib import Path

    home_state = Path.home() / ".local" / "state" / "hermes"
    for name in ("HERMES_EXECUTION_STATE", "HERMES_OPENRIG_LEDGER_DIR", "OPENRIG_HOME"):
        value = Path(os.environ[name]).resolve()
        assert home_state not in value.parents and value != home_state, name
        assert Path.home() / ".openrig" != value, name


def test_the_test_session_never_publishes_to_a_live_api():
    import os
    from control_plane.event_publisher import default_publisher

    assert "LYSSTACK_CONTROL_URL" not in os.environ
    assert not default_publisher.enabled
