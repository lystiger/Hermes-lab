# Hermes Lab

FastAPI health service application and multi-agent experiment lab / orchestration control root.

## Repository Structure

This repository serves as Hermes' control root: it owns runner code, sprint specifications, prompts, and reports. Sprint specifications can target this repository directly or configure `target_repo` to orchestrate changes across external local Git repositories on Linux, WSL, or native Windows.

### Key Capabilities

- **Multi-Agent Orchestration**: Pluggable agent adapters ([`Antigravity`](file:///home/lystiger/hermes-lab/runner/agents/antigravity.py), [`Claude`](file:///home/lystiger/hermes-lab/runner/agents/claude.py), [`Codex`](file:///home/lystiger/hermes-lab/runner/agents/codex.py)) running isolated phases across dedicated Git worktrees.
- **Execution Backends**: `subprocess` runtime alongside one-shot and sessionful `herdr` agent lifecycle backends.
- **External Repository & Platform Portability**: Clean separation between Hermes control root (`control_root`) and target repositories (`target_repo`) across Linux, WSL, and native Windows without cross-kernel path coupling.
- **Generic Verification & Playwright Support**: Declarative, ordered verification pipeline supporting arbitrary test suites (Playwright E2E browser tests, pytest, uv, npm, etc.) with per-step timeouts, working directories, and sanitized reporting.

## Worktree Layout

Sprint worktrees are organized per sprint, e.g. under `~/hermes-worktrees/hermes-lab-s03/` or `~/hermes-worktrees/hermes-lab-s04/`:

- `integration/` — Target integration branch receiving validated controller merges
- `antigravity/` / `claude/` / `codex/` — Isolated worker worktrees assigned to respective agent phases

## Verification & Playwright E2E Testing

Target projects can declare an ordered `verification` pipeline in the sprint specification. This enables automated end-to-end testing, including Playwright browser test suites and Node/Python verification steps:

```json
{
  "verification": [
    {
      "name": "install-dependencies",
      "cwd": "frontend",
      "command": ["npm", "ci"]
    },
    {
      "name": "playwright-e2e",
      "cwd": "frontend",
      "command": ["npx", "playwright", "test"],
      "timeout_seconds": 600
    }
  ]
}
```

### Verification Pipeline Features:
- **Direct Argv Execution**: Commands execute directly as argv arrays without shell interpolation or risk of command injection.
- **Per-Step Cwd & Timeout**: Each step can run in a relative subdirectory (e.g. `frontend`, `backend`) with an optional step-level `timeout_seconds`.
- **Fail-Fast Enforcement**: Verification halts on first failure, failing with `FAILED_VERIFICATION` or `FAILED_INVALID_VERIFICATION_SPEC`.
- **Isolated Logging & Sanitization**: Stdout and stderr logs are preserved under `~/hermes-runs/`, while sanitized reports (`--export-report`) strip sensitive runtime metadata and tokens.
- **Backwards Compatibility**: Specs omitting `verification` fall back to the legacy isolated venv / pytest workflow.

## Sprint History

- **Sprint 01**: Initial FastAPI health service scaffolding and endpoint implementation (`/health` and `/version`). Merged into `main`. Old worktrees (`~/hermes-lab-agy` and `~/hermes-lab-claude`) cleaned up.
- **Sprint 02**: Worktrees initialized under `~/hermes-worktrees/hermes-lab-s02/`.
- **Sprint 03**: Agent adapters and first-class Codex worker support.
- **Sprint 04**: Execution backend abstraction with subprocess compatibility and one-shot Herdr hosting.
- **Sprint 05**: Reproducible three-agent delivery with Antigravity scaffolding, Claude hardening, and Codex verification.
- **Sprint 06**: External target repository support, generic multi-command verification pipeline (Playwright / npm / uv / pytest), and Codex-first native Herdr session backend with lifecycle and ownership verification.
