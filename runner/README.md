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
│   ├── s05-codex.md          # Independent API verification prompt
│   ├── s06-agy.md            # Session contract scaffold prompt
│   ├── s06-claude.md         # Session backend implementation prompt
│   └── s06-codex.md          # Session lifecycle verification prompt
└── sprints/
    ├── lab-s02.json          # Backwards-compatible Sprint 02 specification
    ├── lab-s03.json          # Claude implementation + Codex verification
    ├── lab-s04.json          # Staged subprocess + Herdr backend workflow
    ├── lab-s05.json          # Three-agent subprocess + Herdr workflow
    └── lab-s06.json          # Codex-first session backend delivery
```

## Repository & Execution Architecture

- **Control Root**: Hermes repository containing `runner/`, `prompts/`, `sprints/`, and `reports/`.
- **Target Repository**: configured Git repository agents change. It must be clean before execution and may be separate from Hermes.
- **Runtime Worktrees**: configured target-repository worktrees. Sprint 03 uses `~/hermes-worktrees/hermes-lab-s03/`:
  - `integration/` (`s03/integration`) - Target integration branch receiving validated phase commits
  - `claude/` (`s03/claude`) - Adapter implementation workspace
  - `codex/` (`s03/codex`) - Independent verification workspace
- **Runtime Logs & Venv**: `~/hermes-runs/<timestamp>_<sprint_id>/`
  - `run_summary.json` - Structured JSON execution summary
  - `runner.log` - Full timestamped controller log output
  - `<phase>_<agent>_stdout.log` / `<phase>_<agent>_stderr.log` - Agent process output logs
  - `handoffs/<index>_<role>_<agent>.md` - Runner-owned phase handoff evidence
  - `venv/` - Isolated temporary Python virtual environment created per run

## Workflow Sequence

1. **Environment & Safety Check**: Verifies the target repository is clean, validates registered agents, and creates or validates target-repository worktrees.
   Clean integration and phase worktrees are reset to their configured starting refs on every run, so prior sprint commits cannot affect a rerun. Dirty or wrongly assigned worktrees fail before reset.
   Sprint specifications may pin an immutable `base_ref`; legacy `base_branch` remains supported. Sprint 04 pins its Sprint 03.1 baseline so reruns do not start from a `main` branch that already contains Sprint 04.
2. **Agent Dispatch**: Resolves the phase agent through the registry. The adapter invokes its CLI and validates its result while writing phase stdout/stderr logs.
   The selected execution backend hosts that unchanged one-shot CLI. `subprocess` is the compatibility reference; `herdr` uses a runner-owned persistent workspace and pane.
3. **Controller Validation**: Recursively compiles Python, enforces the changed-file limit, and requires the configured non-empty handoff.
4. **Controller Integration**: The controller alone stages, commits, and merges the phase. Each later phase is synchronized to the latest integration branch first.
5. **Verification & Testing**:
   - Specs with `verification` run each declared argv command sequentially against the integration worktree.
   - Specs without `verification` retain the legacy isolated venv, `requirements.txt`, and pytest workflow.
   - Final state transitions to `READY_FOR_REVIEW` ONLY if all phases and configured verification succeed without `NO_CHANGES` or failures.

## Fail-Fast Guardrails

- `FAILED_TARGET_REPO_MISSING`: Configured target repository does not exist.
- `FAILED_TARGET_REPO_NOT_GIT`: Configured target is not a Git working tree.
- `FAILED_DIRTY_REPO`: Target repository working tree has uncommitted changes.
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
- `FAILED_INVALID_HANDOFF`: Configured handoff path is unsafe or not a file.
- `FAILED_EXCESSIVE_FILES`: Worktree modified more than `limits.max_changed_files` files.
- `FAILED_UNKNOWN_ROLE`: Phase declares an unsupported role.
- `FAILED_FORBIDDEN_CHANGES`: Verifier modified target source.
- `FAILED_SYNTAX_ERROR`: Python syntax error detected.
- `FAILED_INVALID_CONTEXT_SPEC`: Context configuration, root, path, duplicate, or size setting is invalid.
- `FAILED_CONTEXT_FILE_MISSING`: A configured context file does not exist.
- `FAILED_CONTEXT_FILE_INVALID`: A configured context entry is not a regular file.
- `FAILED_CONTEXT_READ`: A configured context file cannot be read as UTF-8.
- `FAILED_CONTEXT_TOO_LARGE`: Context contents exceed the configured byte limit.
- `FAILED_INVALID_VERIFICATION_SPEC`: Generic verification configuration is malformed or escapes the integration worktree.
- `FAILED_VERIFICATION`: A required generic verification step failed.
- `FAILED_TESTS`: Pytest suite failed in virtual environment.

## Security & Governance Boundaries

- **Controller Git Ownership**: All `git add`, `git commit`, and `git merge` commands are strictly executed by the controller script. Agents edit files only.
- **Worker Git Boundaries**: Antigravity denies writes to worktree and target-repository Git metadata; Claude receives CLI-level denials for Git mutation commands while retaining read-only inspection; Codex is forced into its assigned `workspace-write` sandbox.
- **Isolated Permission Tests**: Antigravity settings paths are injectable, and tests use temporary settings files. Production defaults to `~/.gemini/antigravity-cli/settings.json`.
- **No Remote Operations**: The runner does NOT push to `origin`, merge to `main`, or deploy to external environments.

## Sanitized Run Evidence

Use `--export-report` to write deterministic, reviewable evidence to `reports/<sprint-id>/run-summary.json`, or provide an explicit path. The export contains only sprint status, safe phase fields, test status, and the integration commit. It excludes prompts, model output, test output, errors, tokens, timestamps, and absolute paths.

The export happens after sprint execution, so it cannot affect worker changed-file validation or the integration commit. Default reports live under the Hermes control root, never the external target repository.

## External Target Repositories

Use `target_repo` to run Hermes against another local Git repository:

```json
{
  "sprint_id": "external-example",
  "target_repo": "/path/to/product",
  "base_ref": "main",
  "target_branch": "hermes/external-example",
  "worktree_root": "/path/to/hermes-worktrees/external-example",
  "runs_root": "/path/to/hermes-runs",
  "phases": []
}
```

Hermes derives `control_root` from the runner location unless explicitly configured. Relative `control_root`, `target_repo`, `worktree_root`, and `runs_root` values resolve from the sprint specification directory. Relative phase `prompt_file` values resolve from `control_root`. Legacy `canonical_repo` remains supported as a fallback target when `target_repo` is absent.

Use paths native to the Python environment: Linux paths on Linux, WSL-visible paths under WSL, and Windows paths under native Windows. No cross-kernel path conversion occurs.

## Read-Only Context Bundles

An optional `context` block loads explicit UTF-8 text files from a directory independent of both `control_root` and `target_repo`:

```json
{
  "context": {
    "root": "../Policy Repository",
    "max_bytes": 262144,
    "files": [
      "projects/example/architecture.md",
      "projects/example/constraints.md",
      "operating_system/active_task.md"
    ]
  }
}
```

Relative `context.root` values resolve from the sprint specification directory. Every `context.files` entry must be a unique, non-empty relative path contained by that root. Files must exist, be regular UTF-8 text files, and remain within the root after symlink resolution. Absolute paths and traversal are rejected.

Hermes only reads configured files. It never gives workers filesystem access to the context root and never writes, deletes, renames, or commits context files. Contents are appended to every phase's base prompt in declared order using logical relative identifiers. Specs without `context` receive their original prompt unchanged.

Total file-content size defaults to 256 KiB. `context.max_bytes` may set another positive integer limit; Hermes fails instead of truncating when exceeded. Run summaries and sanitized reports expose only file count and UTF-8 byte count, never context contents, filenames, or absolute paths.

## Generic Verification

Target projects may declare final verification as an ordered top-level array. Every step requires a unique non-empty `name` and a non-empty `command` array containing only strings. Commands execute directly as argv without shell interpretation.

`cwd` is optional and defaults to the integration worktree root. When present, it must be a relative path contained inside that worktree. `timeout_seconds` is optional, must be positive, and overrides the runner timeout for that step. Steps stop on first failure. Per-step stdout and stderr logs stay under the Hermes run directory.

Python/uv example:

```json
{
  "verification": [
    {
      "name": "sync",
      "cwd": "backend",
      "command": ["uv", "sync", "--all-groups"]
    },
    {
      "name": "tests",
      "cwd": "backend",
      "command": ["uv", "run", "pytest"],
      "timeout_seconds": 600
    }
  ]
}
```

Non-Python / Frontend example (including Playwright E2E):

```json
{
  "verification": [
    {
      "name": "install",
      "cwd": "frontend",
      "command": ["npm", "ci"]
    },
    {
      "name": "e2e-playwright",
      "cwd": "frontend",
      "command": ["npx", "playwright", "test"],
      "timeout_seconds": 600
    }
  ]
}
```

This contract is platform-neutral: use executables and paths available to the active Linux, WSL, or native Windows environment. Empty or absent `verification` keeps legacy Python verification for historical sprint specs.

## Phase Roles

Phase behavior comes from `role`, independently from worker identity in `agent`:

- `builder`: target changes required; successful changes are committed and merged.
- `hardener`: target changes optional; changes are committed and merged only when present.
- `verifier`: target changes forbidden; no commit or merge occurs.

This keeps workers replaceable. A future agent may perform any role without changing controller semantics.

```json
{
  "phases": [
    {
      "name": "implementation",
      "role": "builder",
      "agent": "antigravity"
    },
    {
      "name": "hardening",
      "role": "hardener",
      "agent": "claude"
    },
    {
      "name": "verification",
      "role": "verifier",
      "agent": "codex"
    }
  ]
}
```

Role-less historical phases retain legacy behavior: at least one change is required, then committed and merged. Every phase still writes its configured worktree handoff. Hermes captures that content under the run directory, restores or removes the worktree copy, and only then counts, stages, or rejects target changes. Handoff contents never enter summaries or sanitized reports.

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

# Run Sprint 06's Codex-first session backend delivery
python3 runner/run-hermes-sprint.py --spec sprints/lab-s06.json

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
