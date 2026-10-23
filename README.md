# Hermes Runtime

The authoritative engineering execution runtime for job orchestration, task scheduling, agent execution, worktrees, verification, event history, recovery, and provider capacity. LysStack supplies bounded engineering context, policy, and decisions; it does not execute agents or schedule runtime jobs. LysControl is the operator-facing UI and consumes Hermes through REST/SSE.

## Repository Structure

This repository contains Hermes runtime and runner code, sprint specifications, prompts, and reports. Sprint specifications can target this repository directly or configure `target_repo` to orchestrate changes across external local Git repositories on Linux, WSL, or native Windows.

### Key Capabilities

- **Multi-Agent Orchestration**: Pluggable agent adapters ([`Antigravity`](file:///home/lystiger/hermes-lab/runner/agents/antigravity.py), [`Claude`](file:///home/lystiger/hermes-lab/runner/agents/claude.py), [`Codex`](file:///home/lystiger/hermes-lab/runner/agents/codex.py)) running isolated phases across dedicated Git worktrees.
- **Execution Backends**: `subprocess` runtime alongside one-shot and sessionful `herdr` agent lifecycle backends.
- **External Repository & Platform Portability**: Clean separation between Hermes control root (`control_root`) and target repositories (`target_repo`) on Linux without cross-kernel path coupling.
- **Generic Verification & Playwright Support**: Declarative, ordered verification pipeline supporting arbitrary test suites (Playwright E2E browser tests, pytest, uv, npm, etc.) with per-step timeouts, working directories, and sanitized reporting.

## Compatibility Names

`LYSSTACK_CONTROL_URL` and the `LYSSTACK_*` agent-message markers are retained
for existing runner configurations and prompt protocols. They refer to Hermes
Runtime APIs and messages, not a separate LysStack execution service.

## Durable Jobs

Without `DATABASE_URL`, Hermes keeps its job ledger in memory and a restart loses every running job. With it, a restart resumes unfinished goal-planned jobs on its own:

```bash
docker compose up -d postgres                       # container hermes_postgres
psql postgresql://postgres:postgres@localhost:5432/postgres -c "CREATE DATABASE hermes"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hermes .venv/bin/alembic upgrade head
```

The `lysomarchy-hermes-api` service reads `DATABASE_URL` from `~/.config/lysomarchy/hermes-stack.env`. The `hermes_lab` database belongs to the Postgres tests, so live jobs use `hermes`.

On startup, Hermes waits for the previous process's job lease to expire (up to 60s), then rebuilds each job's agents from the settings it was launched with. Finished tasks are kept, interrupted ones run again from a clean worktree, and a usage limit that hasn't reset yet still pauses the job. A job interrupted while planning is planned again. Set `HERMES_AUTO_RESUME=0` to resume jobs by hand with `POST /jobs/{id}/resume`.

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
