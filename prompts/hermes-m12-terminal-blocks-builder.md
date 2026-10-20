# Hermes M12: environment blocks end the job instead of replanning

You are the BUILDER. Repository: this Hermes runtime (Python). Work in this worktree on the sprint branch. Do not touch the console frontend.

## Problem (observed)
When a verifier cannot run a check because the sandbox blocks it (for example `listen EPERM`, Chromium unavailable, or a permission denial), its verdict is "failed" and marked repairable. The runtime then starts a fix phase, replans, and repeats. On 2026-10-20 the M10 review ran three fix verifiers and then stopped with "Exhausted maximum allowed replans (3)". Nothing was wrong with the code: the gates passed every time.

Relevant code: runner/agents/codex.py (verdict parsing, the `repairable` field), runtime/hermes_adapter.py (around the `has_repairable_failure` logic, about line 1338), runtime/events.py, and the planner/replan code under runtime/planning/ and jobs/job_service.py.

## Goal
1. A verdict caused by the environment must not be repairable. Add an explicit environment-block signal to the verdict contract: a `blocked_by` field (or equivalent) that the verifier sets to `environment` when a check could not run for sandbox reasons. A verdict with `blocked_by: environment` is treated as non-repairable: the job ends in a terminal state with a reason that says it was blocked by the environment, and no fix or replan phase is created.
2. Keep the existing replan behaviour for real code defects (repairable failures). Do not weaken it.
3. Parse the signal from the JSON verdict and from the textual REPAIRABLE form, so both agent output styles work.
4. Log one clear event for the terminal block, naming the phase and the reason.

## Constraints
- Do not change the GET /jobs or GET /jobs/{id} response shapes except for the reason text.
- Do not change how replans work for repairable defects.
- Standard library only for new code.

## Tests (pytest, under tests/)
- A verdict with `blocked_by: environment` ends the job without creating a fix phase.
- A repairable defect verdict still creates a fix phase (unchanged behaviour).
- The textual REPAIRABLE: FALSE form is handled.
- The terminal reason names the blocking phase.

## Gates
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider` exits 0. Use the venv.

## Handoff
Write HANDOFF_BUILDER.md: the contract change, the files changed, test results, and what you are unsure about. Use your file-write tool, not a shell heredoc or redirect. Do not run git commands: the controller stages and commits your changes, and it excludes the handoff file.
