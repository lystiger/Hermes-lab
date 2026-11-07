"""Tests for Hermes verification coverage contract (Change 1).

Covers:
1. HERMES VERIFICATION CONTRACT injection for verifier and security roles in runtime/hermes_adapter.py:
   - states to list every failing item, not only the first few.
   - reports coverage as two integers named 'checked' and 'total'.
2. parse_verification_output in runner/agents/codex.py:
   - when checked < total, verdict becomes unproven.
   - when checked or total is missing, verdict is kept as given and a warning is added to runtime metadata.
"""

import json
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from runner.agents.codex import CodexAdapter
from runner.backends.base import ExecutionResult
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode


def _extract_contract(prompt: str) -> str:
    start_tag = "--- HERMES VERIFICATION CONTRACT ---"
    end_tag = "--- END VERIFICATION CONTRACT ---"
    start_idx = prompt.find(start_tag)
    end_idx = prompt.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        return ""
    return prompt[start_idx : end_idx + len(end_tag)]


@pytest.mark.parametrize("role", ["verifier", "security"])
def test_verification_contract_injected_states_exhaustive_findings_and_coverage(role: str):
    """The contract injected for verifier and security roles must require listing every failing item
    and reporting coverage as checked and total integers.
    """
    adapter = HermesActorAdapter()
    task = TaskNode(task_id="t_verify", description="Perform verification.", metadata={"role": role})
    prompt = adapter.build_effective_prompt(base_prompt="Verify deliverables.", role=role, task=task)

    contract = _extract_contract(prompt)
    assert contract, f"HERMES VERIFICATION CONTRACT missing in effective prompt for role '{role}'"

    # Must say: list every failing item, not only the first few
    assert "list every failing item, not only the first few" in contract.lower(), (
        f"Contract for role '{role}' must state to list every failing item, not only the first few. "
        f"Got contract:\n{contract}"
    )

    # Must report coverage as two integers named checked and total
    assert "checked" in contract, f"Contract for role '{role}' must name 'checked' field"
    assert "total" in contract, f"Contract for role '{role}' must name 'total' field"


def test_verification_contract_not_injected_for_builder_role():
    """Non-verification roles must not receive the verification contract."""
    adapter = HermesActorAdapter()
    task = TaskNode(task_id="t_build", description="Build deliverables.", metadata={"role": "builder"})
    prompt = adapter.build_effective_prompt(base_prompt="Build stuff.", role="builder", task=task)
    assert "--- HERMES VERIFICATION CONTRACT ---" not in prompt


@pytest.mark.parametrize("original_verdict", ["passed", "failed"])
def test_parse_verification_output_checked_less_than_total_becomes_unproven(original_verdict: str):
    """When checked < total, parse_verification_output must make the verdict unproven."""
    payload = {
        "verdict": original_verdict,
        "summary": "Partial verification performed",
        "checked": 4,
        "total": 10,
        "findings": ["finding 1"] if original_verdict == "failed" else [],
    }
    raw_output = json.dumps(payload)
    parsed = CodexAdapter.parse_verification_output(raw_output)

    assert parsed is not None
    assert parsed.get("verdict") == "unproven", (
        f"Expected verdict 'unproven' when checked (4) < total (10), got '{parsed.get('verdict')}'"
    )


def test_parse_verification_output_fenced_json_checked_less_than_total_becomes_unproven():
    """Markdown fenced JSON with checked < total also produces unproven verdict."""
    raw_output = """
Here is the verification result:
```json
{
  "verdict": "passed",
  "summary": "Only verified 2 out of 5 checks",
  "checked": 2,
  "total": 5,
  "findings": []
}
```
"""
    parsed = CodexAdapter.parse_verification_output(raw_output)
    assert parsed is not None
    assert parsed.get("verdict") == "unproven"


@pytest.mark.parametrize(
    "payload_override",
    [
        {},  # neither checked nor total
        {"checked": 5},  # total missing
        {"total": 5},  # checked missing
    ],
)
def test_parse_verification_output_missing_coverage_keeps_verdict_and_warns(payload_override: Dict[str, Any]):
    """When checked or total is missing:
    - verdict is kept as given
    - a warning is added to the runtime metadata.
    """
    payload = {
        "verdict": "passed",
        "summary": "Verification completed without full coverage telemetry",
        "findings": [],
        **payload_override,
    }
    raw_output = json.dumps(payload)
    parsed = CodexAdapter.parse_verification_output(raw_output)

    assert parsed is not None
    assert parsed.get("verdict") == "passed", (
        f"Verdict must be kept as given ('passed'), got '{parsed.get('verdict')}'"
    )

    warning = parsed.get("warning") or parsed.get("warnings")
    assert warning, (
        f"Expected a warning in parsed verification runtime metadata when coverage is incomplete: {payload_override}. "
        f"Got metadata keys: {list(parsed.keys())}"
    )


def test_validate_result_missing_coverage_records_warning_in_runtime_metadata():
    """CodexAdapter.validate_result preserves verdict and attaches warning in result.runtime_metadata
    when checked or total is missing.
    """
    payload = {
        "verdict": "passed",
        "summary": "Check passed without checked/total",
        "findings": [],
    }
    res = ExecutionResult(
        command=["codex"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
        backend="mock",
    )
    context = SimpleNamespace(phase={"role": "verifier"})
    adapter = CodexAdapter()
    adapter.validate_result(res, context)

    assert res.runtime_metadata.get("verdict") == "passed"
    warning = res.runtime_metadata.get("warning") or res.runtime_metadata.get("warnings")
    assert warning, (
        "Expected warning to be present in result.runtime_metadata when checked/total is missing. "
        f"Metadata: {res.runtime_metadata}"
    )


def test_validate_result_checked_less_than_total_records_unproven_verdict():
    """CodexAdapter.validate_result records unproven verdict in result.runtime_metadata
    when checked < total.
    """
    payload = {
        "verdict": "passed",
        "summary": "Partial check",
        "checked": 3,
        "total": 10,
        "findings": [],
    }
    res = ExecutionResult(
        command=["codex"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
        backend="mock",
    )
    context = SimpleNamespace(phase={"role": "verifier"})
    adapter = CodexAdapter()
    adapter.validate_result(res, context)

    assert res.runtime_metadata.get("verdict") == "unproven"
