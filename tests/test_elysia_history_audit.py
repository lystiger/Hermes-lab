import json

import pytest

from tools.elysia_history_audit import main

SENTINEL_ERROR = "SENTINEL-ERROR-TEXT-7f3a"
SENTINEL_BLOCKED = "SENTINEL-BLOCKED-REASON-9c1d"
SENTINEL_LOG = "SENTINEL-RUNNER-LOG-4b8e"


def _write_run(root, run_id, *, status="COMPLETED", completed=True, extra=None, files=None):
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    job = {
        "id": run_id,
        "sprintId": "sprint-synthetic",
        "status": status,
        "createdAt": "2026-01-01T10:00:00Z",
        "completedAt": "2026-01-01T10:30:00Z" if completed else None,
        "branch": "synthetic/branch",
        "phases": [{"id": "phase-a", "role": "builder"}],
        "tasks": [{"id": "task-a", "role": "builder"}],
    }
    job.update(extra or {})
    (run_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    for name, text in (files or {}).items():
        (run_dir / name).write_text(text, encoding="utf-8")
    return run_dir


def _run_audit(tmp_path, roots, out_name="out"):
    out = tmp_path / out_name
    assert main([*map(str, roots), "--out", str(out)]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    split = json.loads((out / "split.json").read_text(encoding="utf-8"))
    return out, manifest, split


def _run_by_id(manifest, run_id):
    return next(run for run in manifest["runs"] if run["id"] == run_id)


def _family_of(manifest, run_id):
    return _run_by_id(manifest, run_id)["family_id"]


def _family(manifest, family_id):
    return next(f for f in manifest["families"] if f["family_id"] == family_id)


def test_statuses_are_recorded_as_definitive_when_complete(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_cc01", status="COMPLETED")
    _write_run(root, "run_20260101_100000_fa01", status="FAILED")
    _write_run(root, "run_20260101_100000_bl01", status="BLOCKED")

    _, manifest, _ = _run_audit(tmp_path, [root])

    assert _run_by_id(manifest, "run_20260101_100000_cc01")["status"] == "COMPLETED"
    assert _run_by_id(manifest, "run_20260101_100000_fa01")["status"] == "FAILED"
    assert _run_by_id(manifest, "run_20260101_100000_bl01")["status"] == "BLOCKED"
    for run_id in ("run_20260101_100000_cc01", "run_20260101_100000_fa01", "run_20260101_100000_bl01"):
        family = _family(manifest, _family_of(manifest, run_id))
        assert family["status"] == "definitive"
        assert family["reasons"] == []


def test_executing_run_is_flagged_and_needs_review(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_ex01", status="RUNNING", completed=False)

    _, manifest, split = _run_audit(tmp_path, [root])

    run = _run_by_id(manifest, "run_20260101_100000_ex01")
    assert run["flags"]["executing"] is True
    assert "executing_run" in run["reasons"]
    family = _family(manifest, run["family_id"])
    assert family["status"] == "needs_review"
    assert run["family_id"] in split["excluded_needs_review"]


def test_simulated_run_is_flagged_and_needs_review(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_sm01", extra={"metadata": {"dryRun": True}})

    _, manifest, split = _run_audit(tmp_path, [root])

    run = _run_by_id(manifest, "run_20260101_100000_sm01")
    assert run["flags"]["simulated"] is True
    assert "simulated_run" in run["reasons"]
    assert run["family_id"] in split["excluded_needs_review"]


def test_retry_family_stays_together(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_rt01", status="FAILED")
    _write_run(root, "run_20260102_100000_rt01", extra={
        "retryHistory": [{"runId": "run_20260101_100000_rt01", "status": "FAILED"}],
    })

    _, manifest, split = _run_audit(tmp_path, [root])

    first = _family_of(manifest, "run_20260101_100000_rt01")
    second = _family_of(manifest, "run_20260102_100000_rt01")
    assert first == second
    family = _family(manifest, first)
    assert family["members"] == ["run_20260101_100000_rt01", "run_20260102_100000_rt01"]
    assert family["status"] == "definitive"
    assert first in split["development"] + split["held_out"]


def test_retry_with_different_task_graph_is_ambiguous_and_excluded(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_mm01")
    _write_run(root, "run_20260102_100000_mm01", extra={
        "retryHistory": [{"runId": "run_20260101_100000_mm01"}],
        "tasks": [{"id": "task-b", "role": "reviewer"}],
    })

    _, manifest, split = _run_audit(tmp_path, [root])

    original = _family_of(manifest, "run_20260101_100000_mm01")
    retry = _family_of(manifest, "run_20260102_100000_mm01")
    assert original != retry
    for family_id in (original, retry):
        family = _family(manifest, family_id)
        assert family["status"] == "needs_review"
        assert "retry_link_mismatch" in family["reasons"]
        assert family_id in split["excluded_needs_review"]
        assert family_id not in split["development"] + split["held_out"]


def test_duplicate_run_id_is_ambiguous_and_excluded(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root / "first", "run_20260101_100000_dp01")
    _write_run(root / "second", "run_20260101_100000_dp01")

    _, manifest, split = _run_audit(tmp_path, [root])

    runs = [run for run in manifest["runs"] if run["id"] == "run_20260101_100000_dp01"]
    assert len(runs) == 2
    for run in runs:
        assert "duplicate_id" in run["reasons"]
        assert run["family_id"] in split["excluded_needs_review"]
        assert run["family_id"] not in split["development"] + split["held_out"]


def _write_many_families(root, count):
    for index in range(count):
        _write_run(root, f"run_20260101_{index:06d}_s{index:03d}")


def test_split_is_disjoint_and_covers_definitive_families(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_many_families(root, 60)
    _write_run(root, "run_20260101_999999_ex99", status="RUNNING", completed=False)

    _, manifest, split = _run_audit(tmp_path, [root])

    development = set(split["development"])
    held_out = set(split["held_out"])
    assert development and held_out
    assert development.isdisjoint(held_out)

    definitive = {f["family_id"] for f in manifest["families"] if f["status"] == "definitive"}
    assert development | held_out == definitive
    assert len(definitive) == 60

    excluded = set(split["excluded_needs_review"])
    assert excluded.isdisjoint(development | held_out)
    assert _family_of(manifest, "run_20260101_999999_ex99") in excluded


def test_split_is_deterministic_across_repeated_runs(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_many_families(root, 40)

    first_out, first_manifest, _ = _run_audit(tmp_path, [root], out_name="first")
    second_out, second_manifest, _ = _run_audit(tmp_path, [root], out_name="second")

    assert (first_out / "split.json").read_bytes() == (second_out / "split.json").read_bytes()
    assert (first_out / "manifest.json").read_bytes() == (second_out / "manifest.json").read_bytes()
    assert first_manifest == second_manifest


def test_out_inside_git_repository_is_rejected(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_gt01")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    with pytest.raises(SystemExit, match="git repository"):
        main([str(root), "--out", str(repo / "out")])
    assert not (repo / "out").exists()


def test_out_overlapping_input_root_is_rejected(tmp_path):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_ov01")

    with pytest.raises(SystemExit, match="input root"):
        main([str(root), "--out", str(root / "out")])
    with pytest.raises(SystemExit, match="input root"):
        main([str(root), "--out", str(root)])
    assert not (root / "out").exists()


def test_error_and_blocked_text_never_reaches_outputs(tmp_path, capsys):
    root = tmp_path / "roots" / "a"
    _write_run(root, "run_20260101_100000_se01", status="FAILED", extra={
        "error": SENTINEL_ERROR,
        "blockedReason": SENTINEL_BLOCKED,
        "tasks": [{"id": "task-a", "role": "builder", "error": SENTINEL_ERROR,
                   "blockedReason": SENTINEL_BLOCKED}],
    }, files={"runner.log": f"step ok\n{SENTINEL_LOG}\n"})
    _write_run(root, "run_20260101_100000_se02", status="BLOCKED", extra={
        "blockedReason": SENTINEL_BLOCKED,
    })

    out, _, _ = _run_audit(tmp_path, [root])
    printed = capsys.readouterr().out

    for name in ("manifest.json", "split.json"):
        text = (out / name).read_text(encoding="utf-8")
        for sentinel in (SENTINEL_ERROR, SENTINEL_BLOCKED, SENTINEL_LOG):
            assert sentinel not in text
    for sentinel in (SENTINEL_ERROR, SENTINEL_BLOCKED, SENTINEL_LOG):
        assert sentinel not in printed
