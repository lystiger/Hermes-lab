# BUG: A verifier task that reports "failed" is recorded as SUCCEEDED

- **ID:** BUG-verifier-failed-verdict-recorded-as-succeeded
- **Status:** Open. Not fixed. Recorded for a later fix round.
- **Area:** `runtime/hermes_adapter.py` (verdict parsing and task status), Claude agent output
- **Severity:** High. A read-only task can report "failed", and the job still runs its dependents as if the task passed.
- **Date opened:** 2026-11-06
- **Found in:** HASC-Twin J1, job `run_20261106_145253_50df2363`, task `T3_tests_first`

## Symptom

The planner gave `T3_tests_first` the role `verifier`. The goal said "Tests first (Verifier role)", and the planner read that as the Hermes role. Claude ran it read-only, wrote no files, and ended its output with:

```json
{
  "verdict": "failed",
  "summary": "T3 deliverables are absent: the three contract test files in tests/unit/ and docs/acceptance-criteria.md were not written. ...",
  "repairable": true,
  "blocked_by": null,
  "findings": [ "..." ]
}
```

Claude exited with code 0. Hermes recorded the task as `SUCCEEDED`, with the observation "Agent claude completed task T3_tests_first with exit code 0". Dependent tasks (T4, T5, T6) then ran without the tests. The job only blocked at the final Codex check, after three repair cycles, because the tests-first evidence was missing.

## Expected

A verifier task whose verdict is `failed` gets status `failed`. If it is `repairable`, the repair path in `runtime/engine.py` (around line 880) runs, the same way it does for Codex.

## Where the evidence is

- Agent output: `~/Work/Hermes/runs/run_20261106_145253_50df2363/T3_tests_first_claude_stdout.log`. The verdict JSON is inside the final `"type":"result"` stream-json event, as an escaped string in a fenced ```json block.
- Task status: `GET /jobs/run_20261106_145253_50df2363/tasks`. `T3_tests_first` shows `SUCCEEDED`, actor `claude`.

## Code path

`runtime/hermes_adapter.py`:
- Around line 1373: if `runtime_meta` has no `verdict` and the role is `verifier`, the adapter calls `CodexAdapter.parse_verification_output(stdout_text, stderr_text)`. Exceptions are swallowed (`except Exception: pass`).
- Around line 1489: the status is `failed` only if `runtime_meta["verdict"]` is `failed`/`fail`. Otherwise exit code 0 gives `succeeded`.

## Likely cause (not confirmed)

`CodexAdapter.parse_verification_output` expects Codex's output format. Claude's stdout is stream-json, so the verdict sits inside the `result` field as an escaped string, not as raw JSON text. The parser probably finds nothing, or throws and is silenced. `verdict` stays unset, and exit code 0 wins.

Not yet checked: whether `runner/agents/claude.py` puts a verdict in `runtime_metadata`, and whether Antigravity verifiers have the same gap.

## Suggested fix (for the fix round)

1. Parse the verdict from the Claude `result` event (and the Antigravity equivalent), not only from Codex output.
2. Make the safe default fail closed: a `verifier` or `security` task with exit code 0 and no verdict that can be parsed becomes `failed` (not repairable), not `succeeded`.
3. Add a test that feeds the T3 stdout log above through the adapter and expects status `failed`, verdict `failed`, repairable `true`.

## Related

- The planner assigning `verifier` to a task whose goal text asks it to write files. That came from goal wording ("Verifier role"). Possible guard: the planner could warn when a verifier task's description asks it to "write" files.
