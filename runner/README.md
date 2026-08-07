# Hermes Sprint Runner (Sprint 02)

Automated controller framework for orchestrating multi-agent sprint workflows across isolated Git worktrees.

## Overview

The Hermes Sprint Runner turns the manual Sprint 01 agent workflow into an automated, reproducible pipeline. It orchestrates agent execution across dedicated worktrees, enforces fail-fast governance controls, validates Python syntax and handoff documentation, manages git commits/merges, and runs pytest validation inside isolated Python virtual environments.

## Directory & File Layout

```
~/hermes-lab/
├── runner/
│   ├── run-hermes-sprint.py  # Executable sprint runner controller script
│   └── README.md             # Architecture & usage documentation
├── prompts/
│   ├── s02-agy.md            # Scaffold prompt for Antigravity agent phase
│   └── s02-claude.md         # Review & extend prompt for Claude agent phase
└── sprints/
    └── lab-s02.json          # Sprint 02 specification & phase definitions
```

## Worktree & Execution Architecture

- **Canonical Repository**: `~/hermes-lab` (`main` branch)
- **Runtime Worktrees**: `~/hermes-worktrees/hermes-lab-s02/`
  - `integration/` (`s02/integration`) - Target integration branch receiving tested phase commits
  - `antigravity/` (`s02/antigravity`) - Isolated workspace for Antigravity scaffold phase
  - `claude/` (`s02/claude`) - Isolated workspace for Claude review & extension phase
- **Runtime Logs & Venv**: `~/hermes-runs/<timestamp>_<sprint_id>/`
  - `run_summary.json` - Structured JSON execution summary
  - `runner.log` - Full timestamped controller log output
  - `venv/` - Isolated temporary Python virtual environment created per run

## Workflow Sequence

1. **Environment Preparation**: Verifies canonical repository status and ensures Git worktrees exist under `~/hermes-worktrees/hermes-lab-s02/`.
2. **Phase 1: Antigravity Scaffold**:
   - Executes Antigravity agent phase using instructions from `prompts/s02-agy.md`.
   - Controller checks for Python syntax errors (`py_compile`).
   - Controller validates file limit (`max_changed_files <= 15`).
   - Controller validates presence of non-empty `HANDOFF_AGY.md`.
   - Controller stages (`git add .`) and commits changes in `s02/antigravity`.
   - Controller merges commit into `s02/integration`.
3. **Phase 2: Claude Review & Extension**:
   - Syncs `s02/claude` worktree with updated `s02/integration`.
   - Executes Claude agent phase using instructions from `prompts/s02-claude.md`.
   - Controller validates Python syntax, file limit, and `HANDOFF_CLAUDE.md`.
   - Controller stages and commits changes in `s02/claude`.
   - Controller merges commit into `s02/integration`.
4. **Verification & Testing**:
   - Controller creates isolated venv in `~/hermes-runs/<run_id>/venv`.
   - Installs dependencies from `integration/requirements.txt`.
   - Runs `pytest` suite against `s02/integration`.
   - If tests pass, final state transitions to `READY_FOR_REVIEW`.

## Fail-Fast Guardrails

The controller fails fast and stops workflow execution upon encountering:
- `FAILED_TIMEOUT`: Execution duration exceeded `limits.timeout_seconds`.
- `FAILED_PERMISSION_DENIED`: Unauthorized file access or system permission errors.
- `FAILED_MISSING_HANDOFF`: Required handoff file (`HANDOFF_AGY.md` / `HANDOFF_CLAUDE.md`) missing or empty.
- `FAILED_EXCESSIVE_FILES`: Worktree modified more than `limits.max_changed_files` files.
- `FAILED_SYNTAX_ERROR`: Python syntax error detected in changed `.py` files.
- `FAILED_TESTS`: Pytest suite returned non-zero exit code.

## Security & Governance Boundaries

- **Controller Git Ownership**: All `git add`, `git commit`, and `git merge` commands are strictly executed by the controller script. Agents edit files only.
- **No Remote Operations**: The runner does NOT push to `origin`, merge to `main`, or deploy to external environments.
- **No Production Access**: Isolated local execution only.

## Usage

### Run Sprint 02 Pipeline
```bash
python3 runner/run-hermes-sprint.py
```

### Dry-Run / Validation Options
```bash
# Validate controller configuration without modifying git state
python3 runner/run-hermes-sprint.py --dry-run

# Run pipeline skipping external agent CLI execution (for controller testing)
python3 runner/run-hermes-sprint.py --skip-agent-execution -v
```
