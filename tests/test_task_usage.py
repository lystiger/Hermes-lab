import json

from fastapi.testclient import TestClient

import main
from runtime.task_usage import append_usage, read_job_usage, task_usage

CLAUDE_STDOUT = json.dumps({
    "type": "result", "num_turns": 5, "total_cost_usd": 0.0047,
    "usage": {"input_tokens": 12, "cache_creation_input_tokens": 15698, "cache_read_input_tokens": 87681, "output_tokens": 1280},
})


def test_claude_usage_counts_cache_writes_reads_cost_and_turns():
    u = task_usage({}, CLAUDE_STDOUT, "")
    assert u == {"input_tokens": 15710, "cached_tokens": 87681, "output_tokens": 1280,
                 "total_tokens": 104671, "cost_usd": 0.0047, "turns": 5}


def test_codex_usage_is_the_total_it_prints_on_stderr():
    u = task_usage({}, "Added the test.", "hook: Stop Completed\ntokens used\n12,861\n")
    assert u["total_tokens"] == 12861 and u["cost_usd"] is None


def test_agent_reported_usage_in_runtime_metadata_is_used():
    u = task_usage({"usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 5}}, "not json", "")
    assert (u["input_tokens"], u["cached_tokens"], u["output_tokens"], u["total_tokens"]) == (100, 5, 20, 125)


def test_job_usage_survives_in_the_run_dir_and_sums_per_task(tmp_path):
    append_usage(tmp_path, {"task_id": "a", **task_usage({}, CLAUDE_STDOUT, "")})
    append_usage(tmp_path, {"task_id": "b", **task_usage({}, "", "tokens used\n1,000")})
    job = read_job_usage(tmp_path)
    assert [t["task_id"] for t in job["tasks"]] == ["a", "b"]
    assert job["tokens"]["total_tokens"] == 105671 and job["costUsd"] == 0.0047


def test_telemetry_endpoint_reads_the_usage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main.Path, "home", lambda: tmp_path)
    append_usage(tmp_path / "hermes-runs" / "run_x", {"task_id": "a", **task_usage({}, CLAUDE_STDOUT, "")})
    body = TestClient(main.app).get("/jobs/run_x/telemetry").json()
    assert body["tokens"]["cached_tokens"] == 87681 and body["costUsd"] == 0.0047 and body["tasks"][0]["task_id"] == "a"
