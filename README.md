# Hermes Lab

FastAPI health service application and agent experiment lab.

## Repository Structure

This repository is Hermes' control root: it owns runner code, sprint specifications, prompts, and reports. Sprint specifications may set `target_repo` to orchestrate changes in any local Git repository; target worktrees and Git branches belong to that repository.

## Worktree Layout

Sprint 03 worktrees are organized under `~/hermes-worktrees/hermes-lab-s03/`:

- `~/hermes-worktrees/hermes-lab-s03/integration` (Branch: `s03/integration`)
- `~/hermes-worktrees/hermes-lab-s03/claude` (Branch: `s03/claude`)
- `~/hermes-worktrees/hermes-lab-s03/codex` (Branch: `s03/codex`)

Sprint 04 uses the equivalent `integration`, `claude`, and `codex` layout under `~/hermes-worktrees/hermes-lab-s04/` with `s04/*` branches.

## Sprint History

- **Sprint 01**: Initial FastAPI health service scaffolding and endpoint implementation (`/health` and `/version`). Merged into `main`. Old worktrees (`~/hermes-lab-agy` and `~/hermes-lab-claude`) cleaned up.
- **Sprint 02**: Worktrees initialized under `~/hermes-worktrees/hermes-lab-s02/`.
- **Sprint 03**: Agent adapters and first-class Codex worker support.
- **Sprint 04**: Execution backend abstraction with subprocess compatibility and one-shot Herdr hosting.
- **Sprint 05**: Reproducible three-agent delivery with Antigravity scaffolding, Claude hardening, and Codex verification.
- **Sprint 06**: Planned Codex-first native Herdr session backend with lifecycle and ownership verification.
