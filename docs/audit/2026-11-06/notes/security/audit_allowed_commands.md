# Audit: `allowedCommands` mechanism

Scope: read-only trace of how `allowedCommands` is parsed, stored, matched and enforced, and whether rtk rewriting, `*` handling or job metadata can widen it. No other file was edited, no POST was sent to localhost:8000, and agy was not run.

Paths are relative to the worktree root. Line numbers are from the checked-out branch.

## 1. Short answers

| Question in the brief | Finding | Confidence |
|---|---|---|
| Entries are prefixes? | The repo writes each entry as an exact rule `command(<entry>)`, and `runner/README.md` says commands are "exact declarations". The agy 1.5.2 binary's embedded help says `command(<prefix>)` and `command(<binary_and_subcommand>)`. The two disagree. Matching is decided by agy, which this repo does not contain. | Conflict, unverified |
| `*` is literal? | The repo does not special-case `*`. It passes `command(*)` through verbatim, and nothing rejects it. agy's embedded help lists `command(*)` among wildcard grants and says "never `command(*)`", so in agy it is probably a wildcard. | Likely wrong in effect, unverified |
| rtk rewrites commands first? | rtk is only a Claude Code `PreToolUse` Bash hook (`~/.claude/settings.json:22-26`, `rtk hook claude`). Nothing in the repo runs rtk for agents, and the agy settings file has no hooks. Claude agents do not read `allowedCommands` at all, so rtk has no allowlist to bypass. | Verified for the repo; the Claude hook's interaction with `claude -p` is unverified |
| Can job metadata widen prefix matching? | Not through metadata injection. The `/jobs/goal` caller sets `allowedCommands` directly (`main.py:526`, `:566`), and nothing else in the runtime produces a `permissions` value. The real widening lever is the API caller, plus the separate `antigravitySkipPermissions` flag. | Verified |

## 2. Data flow

1. **Parse.** `main.py:526` declares `allowedCommands: List[str] = Field(default_factory=list, max_length=50)`. This limits the list length only. Entries are not checked for emptiness, length, characters or form. The comment at `main.py:525` says "Exact commands agents may run".
2. **Map to job permissions.** `main.py:566` sends `permissions={"commands": payload.allowedCommands}` (or `None` if empty) into `job_launcher.launch_goal_background`. `jobs/job_launcher.py:601` stores it in the job metadata, which is persisted and reloaded on resume (`main.py:592-600`, "Recovers and resumes ... from the canonical event store").
3. **Job default.** `jobs/job_launcher.py:505` sets `default_permissions=meta.get("permissions")`. `runtime/hermes_adapter.py:238` keeps it as `self.default_permissions`.
4. **Per-task selection.** `runtime/hermes_adapter.py:1328-1331` builds each agent's `phase["permissions"]` in this order: `task.metadata["permissions"]`, then `task.metadata["phase"]["permissions"]`, then the job default. The first truthy value wins completely; the lists are not merged.
5. **Enforce (Antigravity only).** `runner/agents/antigravity.py:40-48` calls `scoped_antigravity_permissions(..., allowed_commands=permissions.get("commands", ()))` around the run.
6. **Write rules.** `runner/agents/permissions.py:59` runs `allow_rules.extend(f"command({command})" for command in allowed_commands)`. The entry is inserted with no escaping. Fixed defaults are at `:47-58` (`read_file`/`write_file` on the worktree, read on the target `.git`, `command(pwd)`, `command(ls -la)`, `command(pwd && ls -la)`, `command(python3 -m pytest -q)`). Deny rules are at `:60-65` (`write_file` on both `.git` paths).
7. **Restore.** The settings file is `~/.gemini/antigravity-cli/settings.json` by default (`permissions.py:11-14`). Its bytes are snapshotted at `:16-20` and restored at `:76-80`. The restore is in `finally`, so it does not run on SIGKILL or a power loss.

There is no other consumer of `allowed_commands`. Grep for `allowed_commands`, `allowedCommands` and `permissions` shows the only readers are `permissions.py`, `antigravity.py:46` and `hermes_adapter.py:1328`.

## 3. Enforcement coverage by agent

- **Antigravity (`agy`)**: the only agent that uses the list. It is enforced by agy at run time, and the repo cannot check agy's matcher. Headless agy denies anything not allowed (per the job brief; not re-verified).
- **Claude** (`runner/agents/claude.py`): ignores `permissions`. It runs `--permission-mode dontAsk` (`:75`) with `allowedTools` defaulting to `["Bash", "Edit", "Write", "Skill"]` (`:59`), so all Bash is allowed. Git mutation subcommands are blocked by name patterns (`:33-50`). A job that sets `allowedCommands` and uses Claude gets no command restriction, and nothing says so.
- **Codex** (`runner/agents/codex.py`): no reference to `permissions` or `allowed_commands`. Same as Claude: silently ignored.
- **Validation**: `runner/run-hermes-sprint.py:719-737` checks that `permissions` is an object and that `commands` is a list of non-empty strings. It is called only from `:134` in the spec-driven sprint runner. The goal route (`main.py:540-575` → `job_launcher.launch_goal_background`) never reaches it, so goal-route `allowedCommands` is not validated.

## 4. Can the list be widened?

Ways a job's allowlist can grow beyond what its author intended, ranked by how easily they happen.

**a. Direct API input (confirmed).** Whoever can reach `POST /jobs/goal` chooses `allowedCommands` in full, up to 50 entries of any content. Auth on this route is covered by the HTTP API audit, not here. Within this mechanism, nothing limits what can be granted.

**b. No internal producer of `permissions` (confirmed).** Planner tasks are built in `runtime/planning/contracts.py:66-82`, and that metadata dict has no `permissions` key. Repair and re-check tasks copy metadata (`runtime/engine.py:925-940`) but add no `permissions`. A grep for `"permissions"` in `runtime/` and `jobs/` finds only the reads listed in section 2. So a model-written plan cannot add or widen a command grant. Task-level override exists in code (`hermes_adapter.py:1328-1330`) but no goal path sets it.

**c. Entry text becomes rule text (confirmed; effect in agy unverified).** The entry goes into `command({entry})` unescaped (`permissions.py:59`). An entry such as `ls) or command(*` would produce `command(ls) or command(*)`. Whether agy parses that as two rules is not verified. Entries with `(`, `)`, `*` or newlines have no legitimate use here and are not rejected.

**d. Shared settings file (confirmed; race effect is reasoned, not reproduced).** The settings file is global to the user's account, not per run. Two overlapping antigravity runs break the byte-exact restore. Run A snapshots O and writes O+A. Run B snapshots O+A and writes O+A+B. If A restores first (O), then B restores O+A, so A's grants persist after A has finished. This is a race and needs two runs at once.

**e. Leftovers in the current file (observed).** `~/.gemini/antigravity-cli/settings.json` (read-only inspection) has 66 allow rules, 12 of which name `hermes-worktrees` paths from four earlier run IDs (`run_20261029_…`), plus 27 trusted workspaces. The cause is not established. It could predate the restore logic, or it could be the race in (d). Either way, per-worktree write grants are accumulating in the user's global agy config. The current file has no leftover `command(...)` grants from job allowlists.

## 5. `*` and empty entries

- `*`: the repo writes `command(*)` as-is. No code checks for it in `main.py`, `permissions.py` or the sprint validator. The agy 1.5.2 binary's embedded text says `command(*)` is a wildcard to avoid, so an allowlist entry of `*` should be assumed to grant every command. This is consistent with the brief's "`*` literal" note only in the sense that the repo does not interpret it. It is not a reason to trust it.
- Empty entries: `main.py:526` allows `""`, which produces `command()`. The agy 1.5.2 release notes in its binary say an empty compound `()` "now matches nothing", so this is probably mitigated in that version. The installed version is 1.5.2; the repo does not pin agy.

## 6. Other bypass paths checked

- `antigravitySkipPermissions` (`main.py:534`, `jobs/job_launcher.py:509`, `runner/agents/antigravity.py:30-31`) passes `--dangerously-skip-permissions`, which removes the allowlist entirely. The skip-permissions audit covers this in depth. It is the larger lever here: a job can set both the flag and any allowlist, and the allowlist then does nothing.
- The denial check (`runner/agents/denials.py`, `antigravity.py:64-148`) reads agy's stdout and stderr after the run. It does not prevent commands from running; it only fails the task if denials are reported.

## 7. Risks ranked by likelihood × impact

| # | Risk | Likelihood | Impact | Smallest guardrail |
|---|---|---|---|---|
| 1 | Any `/jobs/goal` caller sets an arbitrary allowlist, including interpreters and `*` (`main.py:526`, `:566`) | Medium (depends on the HTTP API audit) | High | Pydantic item validator on `allowedCommands`: non-empty after strip, max 200 chars, no `(`, `)`, `*`, or newline. Reject bare interpreters (`python`, `python3`, `sh`, `bash`, `env`, `node`, `uv`) with 400. |
| 2 | Grants persist in the user's global agy settings (`permissions.py:16-20`, `:76-80`), as shown by the 12 leftover rules | Medium (observed leftovers; race needs overlap) | Medium | Remove only the rules this run added, instead of restoring old bytes; or serialize runs with a file lock around the context manager. |
| 3 | `allowedCommands` matching is prefix in agy but exact in the repo's docs; no test pins which | Medium | High | Add a test with a harmless command against agy, pinned to the installed version, before relying on exact-match semantics. Until then, enforce the entry form in risk 1. |
| 4 | Silently ignored for Claude and Codex tasks (`claude.py:59`, `codex.py`) | High (misconfiguration) | Medium | Return 400 when `allowedCommands` is set and the job has any non-antigravity agent, or add `allowlistEnforcedBy` to the job response. |
| 5 | Entry text injected into the rule string (`permissions.py:59`) | Low | Medium | Same character check as risk 1, plus a unit test with `)` in an entry. |
| 6 | Empty or whitespace entries become `command()` or `command(  )` (`main.py:526`) | Low (agy 1.5.2 says `()` now matches nothing) | Medium | Reject blank entries in the item validator from risk 1. |
| 7 | rtk `PreToolUse` hook rewrites Bash in Hermes Claude runs before Claude's own rules see the command | Low for the allowlist (Claude has none) | Low–medium | Confirm whether `claude -p` loads `~/.claude/settings.json` hooks and whether rewritten commands are re-checked. Not verified here. |

## 8. Not verified (and what would settle it)

- agy's real matching rule (prefix or exact, and whether `command(*)` is a wildcard): run a harmless `command(pwd)`-style probe in an isolated `HOME` and watch which commands are allowed. This needs an agy run and was out of scope.
- Whether overlapping runs happen in practice: check the runner's concurrency for antigravity tasks and the timestamps of the 4 leftover run IDs.
- Whether `claude -p` runs the rtk hook and re-checks rewritten commands: run one `claude -p` in a throwaway directory with a harmless Bash call and inspect the hook output.

## 9. Project check

Ran `HERMES_LAB_CHECK=1 .venv/bin/python -m pytest -q -p no:cacheprovider`: **18 failed, 1041 passed, 7 skipped, 7 warnings**. All 18 failures are in `tests/test_elysia_history_audit.py` and fail with `SystemExit: error: --out must not be inside a git repository`, raised from the tool itself. They are not caused by this audit (no code was changed). They are most likely from running in a git worktree; not investigated further.
