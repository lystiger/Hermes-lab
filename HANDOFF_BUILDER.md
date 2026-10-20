# Hermes M12 builder handoff

Contract change: Codex JSON and textual verdicts now parse `blocked_by: environment`. Such verdicts force `repairable: false` and `trigger_replan: false`. `VerificationResult` carries the signal, and the engine terminates in `BLOCKED` during `VERIFYING` without creating repair or replan work. A `verification.blocked` event records the phase and reason.

Files changed:
- `runner/agents/codex.py`
- `runtime/hermes_adapter.py`
- `runtime/verification.py`
- `runtime/engine.py`
- `runtime/events.py`

Tests:
- Parser smoke checks for JSON and textual environment-blocked verdicts passed.
- Python compilation and `git diff --check` passed.
- Required pytest gate was started with the specified venv; it reached 23 passing tests and then stalled in this sandbox with no failure output. It was not possible to obtain an exit code.

Uncertain: no new dedicated pytest file was added because the existing focused suite stalls after its first test in this sandbox. Ordinary repairable failures remain on the existing repair/replan path.
