# Hermes Sprint Runner

Automated controller framework for orchestrating adapter-backed agent workflows across isolated Git worktrees.

## Overview

The runner supports Antigravity, Claude, and Codex through a common registry. Adapters own CLI construction and result validation. Execution backends own process hosting, output capture, and timeouts. The controller retains worktree governance, handoff and change validation, Git commits and merges, integration tests, summaries, and final status.

## Directory & File Layout

```
~/hermes-lab/
├── runner/
│   ├── run-hermes-sprint.py  # Executable sprint runner controller script
│   ├── agents/               # Agent interface, adapters, registry, permissions
│   ├── backends/             # Subprocess and one-shot Herdr runtimes
│   └── README.md             # Architecture & usage documentation
├── prompts/
│   ├── s02-agy.md            # Scaffold prompt for Antigravity agent phase
│   ├── s02-claude.md         # Review & extend prompt for Claude agent phase
│   ├── s03-claude.md         # Adapter implementation prompt
│   ├── s03-codex.md          # Independent verification prompt
│   ├── s04-claude.md         # Backend implementation prompt
│   ├── s04-codex.md          # Herdr verification prompt
│   ├── s05-agy.md            # Operational API scaffold prompt
│   ├── s05-claude.md         # Runtime hardening prompt
│   └── s05-codex.md          # Independent API verification prompt
└── sprints/
    ├── lab-s02.json          # Backwards-compatible Sprint 02 specification
    ├── lab-s03.json          # Claude implementation + Codex verification
    ├── lab-s04.json          # Staged subprocess + Herdr backend workflow
    └── lab-s05.json          # Three-agent subprocess + Herdr workflow
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
   Clean integration and phase worktrees are reset to their configured starting refs on every run, so prior sprint commits cannot affect a rerun. Dirty or wrongly assigned worktrees fail before reset.
   Sprint specifications may pin an immutable `base_ref`; legacy `base_branch` remains supported. Sprint 04 pins its Sprint 03.1 baseline so reruns do not start from a `main` branch that already contains Sprint 04.
2. **Agent Dispatch**: Resolves the phase agent through the registry. The adapter invokes its CLI and validates its result while writing phase stdout/stderr logs.
   The selected execution backend hosts that unchanged one-shot CLI. `subprocess` is the compatibility reference; `herdr` uses a runner-owned persistent workspace and pane.
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
- `FAILED_UNKNOWN_BACKEND`: The configured execution backend is unsupported.
- `FAILED_HERDR_EXECUTABLE_MISSING`: The Herdr CLI is unavailable.
- `FAILED_HERDR_UNAVAILABLE`: The Herdr server cannot be reached.
- `FAILED_HERDR_PROTOCOL`: Herdr returned malformed JSON or omitted a required runtime ID.
- `FAILED_HERDR_COMMAND`: Workspace, pane, or control execution failed.
- `FAILED_NO_CHANGES`: Agent phase produced zero file changes.
- `FAILED_MISSING_HANDOFF`: Required handoff file missing or empty.
- `FAILED_EXCESSIVE_FILES`: Worktree modified more than `limits.max_changed_files` files.
- `FAILED_SYNTAX_ERROR`: Python syntax error detected.
- `FAILED_TESTS`: Pytest suite failed in virtual environment.

## Security & Governance Boundaries

- **Controller Git Ownership**: All `git add`, `git commit`, and `git merge` commands are strictly executed by the controller script. Agents edit files only.
- **Worker Git Boundaries**: Antigravity denies writes to worktree and canonical Git metadata; Claude receives CLI-level denials for Git mutation commands while retaining read-only inspection; Codex is forced into its assigned `workspace-write` sandbox.
- **Isolated Permission Tests**: Antigravity settings paths are injectable, and tests use temporary settings files. Production defaults to `~/.gemini/antigravity-cli/settings.json`.
- **No Remote Operations**: The runner does NOT push to `origin`, merge to `main`, or deploy to external environments.

## Sanitized Run Evidence

Use `--export-report` to write deterministic, reviewable evidence to `reports/<sprint-id>/run-summary.json`, or provide an explicit path. The export contains only sprint status, safe phase fields, test status, and the integration commit. It excludes prompts, model output, test output, errors, tokens, timestamps, and absolute paths.

The export happens after sprint execution, so it cannot affect worker changed-file validation or the integration commit. Exporting into the canonical repository intentionally leaves that report as an uncommitted file; commit, move, or remove it before the next run because canonical dirty-repository protection remains enforced.

## Execution Backends

Backend selection precedence is phase override, CLI override, sprint specification, then `subprocess`. Unknown backends fail with `FAILED_UNKNOWN_BACKEND`; explicitly selected Herdr never silently falls back.

The Herdr backend checks the Herdr executable, server reachability, and worker executable. It creates one runner-owned workspace, parses workspace and pane IDs from JSON, and runs each existing one-shot agent CLI through a generated Bash argv-array wrapper. Prompts remain data even when they contain quotes, newlines, shell operators, substitutions, Unicode, or Markdown. Stdout, stderr, exit status, and a nonce completion marker preserve the adapter result contract.

Worker panes remain available for inspection by default. Set `keep_herdr_workspace` to `false` only when runner-owned workspace cleanup is desired. The backend never stops the Herdr server or closes pre-existing workspaces.

## Usage

### Run Sprint Pipeline
```bash
python3 runner/run-hermes-sprint.py

# Re-run the Sprint 02 workflow explicitly
python3 runner/run-hermes-sprint.py --spec sprints/lab-s02.json

# Run Sprint 04's staged subprocess/Herdr workflow
python3 runner/run-hermes-sprint.py --spec sprints/lab-s04.json

# Run Sprint 05's three-agent operational API workflow
python3 runner/run-hermes-sprint.py --spec sprints/lab-s05.json

# Deliberately select Herdr globally for specs without phase overrides
python3 runner/run-hermes-sprint.py --spec <spec.json> --backend herdr

# Export safe evidence at the default deterministic path
python3 runner/run-hermes-sprint.py --export-report

# Export safe evidence to a chosen path
python3 runner/run-hermes-sprint.py --export-report /tmp/lab-s03-summary.json
```

### Dry-Run / Validation Options
```bash
# Validate controller logic without modifying git state
python3 runner/run-hermes-sprint.py --dry-run

# Run pipeline skipping external agent CLI execution (for controller testing)
python3 runner/run-hermes-sprint.py --skip-agent-execution -v
```
