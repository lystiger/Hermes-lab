# Hermes Sprint Runner

Automated controller framework for orchestrating adapter-backed agent workflows across isolated Git worktrees.

## Overview

The runner supports Antigravity, Claude, and Codex through a common registry. Adapters own CLI construction and result validation; the controller retains worktree governance, handoff and change validation, Git commits and merges, integration tests, summaries, and final status.

## Directory & File Layout

```
~/hermes-lab/
├── runner/
│   ├── run-hermes-sprint.py  # Executable sprint runner controller script
│   ├── agents/               # Agent interface, adapters, registry, permissions
│   └── README.md             # Architecture & usage documentation
├── prompts/
│   ├── s02-agy.md            # Scaffold prompt for Antigravity agent phase
│   ├── s02-claude.md         # Review & extend prompt for Claude agent phase
│   ├── s03-claude.md         # Adapter implementation prompt
│   └── s03-codex.md          # Independent verification prompt
└── sprints/
    ├── lab-s02.json          # Backwards-compatible Sprint 02 specification
    └── lab-s03.json          # Claude implementation + Codex verification
```

## Worktree & Execution Architecture

- **Canonical Repository**: `~/hermes-lab` (`main` branch - MUST BE CLEAN)
- **Runtime Worktrees**: configured by each sprint specification. Sprint 03 uses `~/hermes-worktrees/hermes-lab-s03/`:
  - `integration/` (`s03/integration`) - Target integration branch receiving validated phase commits
  - `claude/` (`s03/claude`) - Adapter implementation workspace
  - `codex/` (`s03/codex`) - Independent verification workspace
- **Runtime Logs & Venv**: `~/hermes-runs/<timestamp>_<sprint_id>/`
  - `run_summary.json` - Structured JSON execution summary
  - `runner.log` - Full timestamped controller log output
  - `<phase>_<agent>_stdout.log` / `<phase>_<agent>_stderr.log` - Agent process output logs
  - `venv/` - Isolated temporary Python virtual environment created per run

## Workflow Sequence

1. **Environment & Safety Check**: Verifies the canonical repository is clean, validates registered agents, and creates or validates configured worktrees.
2. **Agent Dispatch**: Resolves the phase agent through the registry. The adapter invokes its CLI and validates its result while writing phase stdout/stderr logs.
3. **Controller Validation**: Recursively compiles Python, enforces the changed-file limit, and requires the configured non-empty handoff.
4. **Controller Integration**: The controller alone stages, commits, and merges the phase. Each later phase is synchronized to the latest integration branch first.
5. **Verification & Testing**:
   - Controller creates isolated venv in `~/hermes-runs/<run_id>/venv`.
   - Installs dependencies from `integration/requirements.txt`.
   - Runs the complete `pytest` suite against the integration worktree.
   - Final state transitions to `READY_FOR_REVIEW` ONLY if all phases and tests succeed without `NO_CHANGES` or failures.

## Fail-Fast Guardrails

- `FAILED_DIRTY_REPO`: Canonical repo working tree has uncommitted changes.
- `FAILED_TIMEOUT`: Execution duration exceeded configured timeout.
- `FAILED_PERMISSION_DENIED`: Tool event or process encountered permission denial.
- `FAILED_ANTIGRAVITY_TOOL_ERROR`: Antigravity tool call returned a non-null error.
- `FAILED_CLAUDE_ERROR` / `FAILED_CLAUDE_MAX_TURNS`: Claude returned error or reached max turn limit.
- `FAILED_AGENT_EXECUTABLE_MISSING`: The configured agent CLI is unavailable.
- `FAILED_AGENT_EXECUTION`: An agent CLI returned a non-zero exit.
- `FAILED_CODEX_EMPTY_OUTPUT`: Codex returned successfully without a result.
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

# Re-run the Sprint 02 workflow explicitly
python3 runner/run-hermes-sprint.py --spec sprints/lab-s02.json
```

### Dry-Run / Validation Options
```bash
# Validate controller logic without modifying git state
python3 runner/run-hermes-sprint.py --dry-run

# Run pipeline skipping external agent CLI execution (for controller testing)
python3 runner/run-hermes-sprint.py --skip-agent-execution -v
```
