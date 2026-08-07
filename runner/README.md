# Hermes Sprint Runner (Sprint 02)

Automated controller framework for orchestrating multi-agent sprint workflows across isolated Git worktrees.

## Overview

The Hermes Sprint Runner turns the manual Sprint 01 agent workflow into an automated, reproducible pipeline. It orchestrates agent execution (`agy` and `claude`) across dedicated worktrees, enforces fail-fast governance controls, validates Python syntax and handoff documentation, manages git commits/merges, and runs pytest validation inside isolated Python virtual environments.

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

- **Canonical Repository**: `~/hermes-lab` (`main` branch - MUST BE CLEAN)
- **Runtime Worktrees**: `~/hermes-worktrees/hermes-lab-s02/`
  - `integration/` (`s02/integration`) - Target integration branch receiving tested phase commits
  - `antigravity/` (`s02/antigravity`) - Workspace for Antigravity scaffold phase (`agy`)
  - `claude/` (`s02/claude`) - Workspace for Claude review & extension phase (`claude`)
- **Runtime Logs & Venv**: `~/hermes-runs/<timestamp>_<sprint_id>/`
  - `run_summary.json` - Structured JSON execution summary
  - `runner.log` - Full timestamped controller log output
  - `<phase>_<agent>_stdout.log` / `<phase>_<agent>_stderr.log` - Agent process output logs
  - `venv/` - Isolated temporary Python virtual environment created per run

## Workflow Sequence

1. **Environment & Safety Check**: Verifies canonical repository status (fails immediately if dirty) and ensures Git worktrees exist under `~/hermes-worktrees/hermes-lab-s02/`.
2. **Phase 1: Antigravity Scaffold**:
   - Executes Antigravity agent: `agy -p <prompt> --output-format stream-json --dangerously-skip-permissions`.
   - Captures stdout/stderr logs into run directory.
   - Parses `stream-json` events for tool errors or permission denials.
   - Controller checks Python syntax (`py_compile`).
   - Controller validates file limit (`1 <= changed_files <= 15`).
   - Controller validates presence of non-empty `HANDOFF_AGY.md`.
   - Controller stages (`git add .`) and commits changes in `s02/antigravity`.
   - Controller merges commit into `s02/integration`.
3. **Phase Synchronization**:
   - Resets `s02/claude` worktree onto the latest `s02/integration` HEAD.
   - Verifies `HANDOFF_AGY.md` and Antigravity changes are present before starting Claude.
4. **Phase 2: Claude Review & Extension**:
   - Executes Claude Code headlessly: `claude -p <prompt> --model sonnet --max-turns 30 --permission-mode dontAsk --output-format json`.
   - Captures stdout/stderr logs into run directory.
   - Parses Claude JSON response for `is_error`, max turns exceeded, permission denials, or non-success result.
   - Controller validates Python syntax, file limits, and `HANDOFF_CLAUDE.md`.
   - Controller stages and commits changes in `s02/claude`.
   - Controller merges commit into `s02/integration`.
5. **Verification & Testing**:
   - Controller creates isolated venv in `~/hermes-runs/<run_id>/venv`.
   - Installs dependencies from `integration/requirements.txt`.
   - Runs `pytest` suite against `s02/integration`.
   - Final state transitions to `READY_FOR_REVIEW` ONLY if all phases and tests succeed without `NO_CHANGES` or failures.

## Fail-Fast Guardrails

- `FAILED_DIRTY_REPO`: Canonical repo working tree has uncommitted changes.
- `FAILED_TIMEOUT`: Execution duration exceeded configured timeout.
- `FAILED_PERMISSION_DENIED`: Tool event or process encountered permission denial.
- `FAILED_ANTIGRAVITY_TOOL_ERROR`: Antigravity tool call returned a non-null error.
- `FAILED_CLAUDE_ERROR` / `FAILED_CLAUDE_MAX_TURNS`: Claude returned error or reached max turn limit.
- `FAILED_NO_CHANGES`: Agent phase produced zero file changes.
- `FAILED_MISSING_HANDOFF`: Required handoff file missing or empty.
- `FAILED_EXCESSIVE_FILES`: Worktree modified more than `limits.max_changed_files` files.
- `FAILED_SYNTAX_ERROR`: Python syntax error detected.
- `FAILED_TESTS`: Pytest suite failed in virtual environment.

## Security & Governance Boundaries

- **Controller Git Ownership**: All `git add`, `git commit`, and `git merge` commands are strictly executed by the controller script. Agents edit files only.
- **No Remote Operations**: The runner does NOT push to `origin`, merge to `main`, or deploy to external environments.

## Usage

### Run Sprint Pipeline
```bash
python3 runner/run-hermes-sprint.py
```

### Dry-Run / Validation Options
```bash
# Validate controller logic without modifying git state
python3 runner/run-hermes-sprint.py --dry-run

# Run pipeline skipping external agent CLI execution (for controller testing)
python3 runner/run-hermes-sprint.py --skip-agent-execution -v
```
