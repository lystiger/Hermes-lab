# Audit: worktree isolation

Scope: read-only trace of what an agent can reach outside its assigned worktree, how worktrees are created, synced and cleaned, and whether the controller stops agents writing to the main checkout. No git command was run. No POST was sent to localhost:8000. No file other than this note was edited. Paths are relative to the worktree root. Line numbers are from the checked-out branch.

## 1. Short answers

| Question in the brief | Finding | Confidence |
|---|---|---|
| Can a Claude agent write outside its worktree? | Yes. Claude gets unrestricted `Bash` (`runner/agents/claude.py:59`) and no `--add-dir` or sandbox. Its cwd is only a starting directory. Git mutation is blocked by prefix patterns only (`claude.py:33-51`), which do not stop `/usr/bin/git`, `git -C <dir> push`, or `sh -c`. | Verified from code. Runtime not exercised. |
| Can a Codex agent write outside its worktree? | Mostly not, by design. Codex runs with `--cd <subdir>` and `--sandbox workspace-write` (`runner/agents/codex.py:16-17`, `:22-23`). Writes outside that root should be denied. One recorded session hit a read-only error on the worktree's git index (`console/HANDOFF_HARDENER.md:30-33`). | Config verified. Sandbox boundary not tested here. |
| Can an Antigravity agent write outside its worktree? | Its own permission rules allow writes only inside the worktree (`runner/agents/permissions.py:50-51`). These rules are the sole guard, and `--dangerously-skip-permissions` removes them (`antigravity.py:30-31`). | Verified from code. |
| Are worktrees created and cleaned safely? | Creation is fail-closed and serialized per repo (`runtime/hermes_adapter.py:127-137`, `:494-541`). Cleanup removes only worktrees under the job's own root (`jobs/job_finalizer.py:116`). Goal-path task names are not path-checked (see R5). | Verified from code. |
| Does the controller stop agents writing to the main checkout? | No. The controller checks only the worktree and integration worktree after a run (`hermes_adapter.py:1416-1419`). Nothing checks the main checkout (`target_repo`) afterwards. | Verified from code. |

Test run: `HERMES_LAB_CHECK=1 .venv/bin/python -m pytest -q -p no:cacheprovider` finished with exit 0: **1059 passed, 7 skipped, 7 warnings, 79 subtests passed**. The log is `/tmp/wt_iso_pytest.log`, outside the repo.

## 2. What an agent can reach

Each agent runs as the same OS user (`runner/backends/subprocess_backend.py:28` uses `Popen(command, cwd=cwd)`, with no `env=` or sandbox). The cwd is a subfolder of the worktree (`hermes_adapter.py:1338`; `subdir_path` in `runtime/target_subdir.py:27-29`). Reach by agent type:

| Path | Claude (`Bash`) | Codex (`workspace-write`) | Antigravity (allowlist) |
|---|---|---|---|
| Its own worktree | write | write | write (`permissions.py:50-51`) |
| Integration worktree `worktree_root/integration` | **write via `../integration`** | outside writable root (denied by design) | not in allow rules |
| Sibling task worktrees under `worktree_root` | **write via `../`** | outside root | not in allow rules |
| Main checkout `target_repo` | **write** | outside root | not in allow rules |
| Shared `target_repo/.git` (hooks, config, refs) | **write** | outside root; `.git` file redirects to it | read only (`permissions.py:52-53`); write denied (`:63-64`) if agy honours denies (unverified) |
| `~/.gemini/antigravity-cli/settings.json` | **write** | outside root | not in allow rules, but the agent's own settings are on disk |
| Home directory (`~/`) | **read and write** | outside root | not in allow rules |

The Claude row is the biggest exposure: one `Bash` call can reach every row above. The same `Bash` allowance also gives a route around the git denials in `claude.py:33-51`.

## 3. Worktree creation and cleanup

- **Root.** `worktree_root` defaults to `target_repo/.worktrees` (`hermes_adapter.py:243`). Goal jobs set it to `~/hermes-worktrees/<job_id>` (`jobs/job_launcher.py:579`), and it is stored in job metadata (`:593`). The sprint path takes it from the spec (`jobs/job_launcher.py:266`).
- **Creation.** `_ensure_worktree` runs `git worktree add` under the repo lock (`hermes_adapter.py:494-541`). It refuses a non-empty path that is not a worktree root (`:519-521`). It fails closed on `git` errors (`:534-535`) and raises `WorktreeError` (`:1545-1551`).
- **Root check.** `_is_worktree_root` compares `git rev-parse --show-toplevel` with the path (`hermes_adapter.py:395-420`). The `git reset --hard` and `git clean -fd` reset runs only on a real worktree root (`:510-517`), so a plain subdirectory of the main repo cannot be reset.
- **Dependency seeding.** `_link_virtualenvs` symlinks the main checkout's `.venv` into each new worktree (`hermes_adapter.py:449-462`). The symlink is writable from the worktree, so writes go to the main checkout's venv (R6).
- **Sync.** Each task runs `git fetch . <target_branch>` then `git reset --hard FETCH_HEAD` in its own worktree (`:561-562`). This is fine: it is scoped to the worktree and guarded by `_is_worktree_root`.
- **Cleanup.** `clean_job_worktrees` removes only worktrees whose resolved path is inside the job's `worktree_root` (`jobs/job_finalizer.py:116-117`). It then deletes `task/<job_id>/*` branches and runs `shutil.rmtree(worktree_root)` (`:123`). The rmtree path comes from job metadata, which the controller generates for goal jobs. Low risk.
- **Serialization.** `repo_git_lock` serializes Hermes's own git mutations per repo (`hermes_adapter.py:127-137`). Agents' own `git` calls in `Bash` do not take it.

## 4. Controller and the main checkout

- The integration worktree is authoritative, and task commits merge into it (`hermes_adapter.py:645`, `:659`).
- Agents never get the main checkout as their cwd. Nothing in the goal path verifies it afterwards. `validate_python_syntax`, `inspect_changed_files` and `_commit_and_integrate_changes` look only at the task worktree (`:590-600`, `:574`, `:625`).
- The legacy sprint runner did check the main checkout before a run (`runner/run-hermes-sprint.py:993-994`, "MUST fail if dirty"). The goal path does not carry that check over.

## 5. Ranked risks

Ranked by likelihood × impact. Likelihood reflects that goal jobs run agents with `Bash` (Claude is the default builder) and that planner output is influenced by repository content.

| # | Risk | Likelihood | Impact | Smallest guardrail |
|---|---|---|---|---|
| R1 | Claude `Bash` reaches home, the main checkout, sibling worktrees and the integration worktree (`claude.py:59`, `:75`; no `--add-dir`, no sandbox) | High | High | Run the Claude CLI under an OS sandbox whose only writable path is the worktree (for example `bwrap --ro-bind / / --bind <worktree> <worktree>`). Test that a write outside the worktree fails. Option not verified against Claude Code. |
| R2 | Shared `target_repo/.git` hooks or config writable from Claude `Bash`. The controller's own `git commit` (`hermes_adapter.py:645`) and merge (`:659`) would then run attacker-chosen code as the controller. | Medium | High | Pass `-c core.hooksPath=/dev/null` on every controller git call that commits or merges (`hermes_adapter.py:641-659`). Fail the task if `.git/config` or `.git/hooks` changed during the run. |
| R3 | Main checkout modified during an agent run, and nothing notices (section 4) | Medium | High | Record `git status --porcelain` of `target_repo` before and after each agent run (`hermes_adapter.py:1342-1420`). Fail the task on any change. This is a read-only check. |
| R4 | Antigravity settings file is shared and unlocked. `scoped_antigravity_permissions` snapshots and restores the whole file (`permissions.py:15-20`, `:77-80`) with no lock (`antigravity.py:40-48`; `repo_git_lock` covers git only). Concurrent runs can leave rules behind, and a killed process skips restore. Evidence: 3 distinct stale worktree directories are still referenced in `~/.gemini/antigravity-cli/settings.json`, none of which exists on disk. | High | Medium | Wrap `scoped_antigravity_permissions` in one process-wide lock. Remove rules for worktrees that no longer exist when the context is entered. |
| R5 | Goal-path task names are not path-checked. `task.task_id` from the planner becomes `worktree_root / wt_name` (`hermes_adapter.py:1302`, `:1306`). Planner validation checks only empty and duplicate ids (`runtime/planning/validator.py:71-77`), and `to_task_node` sets no `worktree_dir` (`runtime/planning/contracts.py:57-82`). An id with `/` or `..` can place the worktree, and the agent's cwd, outside `worktree_root`. Git ref rules may reject some forms (unverified). | Low-Medium | High | Validate `task_id` as `^[A-Za-z0-9_-]+$` in `contracts.py:47`. Assert `path.is_relative_to(worktree_root)` in `_ensure_worktree`. |
| R6 | Symlinked `.venv` (`hermes_adapter.py:449-462`) lets an agent write into the main checkout's venv (for example by `pip install`) | Medium | Medium | Stop linking the venv, or hash `target_repo/.venv` before and after the run and fail on change. |
| R7 | Sprint-spec `target_repo` and `worktree_root` are not contained on the `/jobs` path (`jobs/job_launcher.py:265-266`, `:313-314`). The legacy runner has the containment check (`run-hermes-sprint.py:859-870`). | Low | Medium | Apply the same containment check to `jobs/job_launcher.py` before use. |
| R8 | Codex boundary relies on the external sandbox. The `.git` pointer and `.venv` symlink sit near or outside the root. | Low | Medium | Add a test that a write outside the Codex cwd is refused. Keep `--sandbox workspace-write`. |
| — | Cross-reference: `--dangerously-skip-permissions` for Antigravity (`antigravity.py:30-31`, `main.py:534`) removes all of section 2's Antigravity limits. This is covered by `audit_skip_permissions`. | High | High | See that note. |

## 6. Not verified here

- Whether Claude Code's Edit and Write tools refuse paths outside the working directory under `--permission-mode dontAsk`. Bash bypasses them either way, so the R1 conclusion does not depend on it.
- Whether agy honours `deny` rules over `allow` rules (`permissions.py:60-65`).
- Whether git's ref rules reject a planner `task_id` containing `/` or `..` (R5).
- The actual Codex and Claude sandbox behaviour. No agent was run.

## 7. Method and limits

- Read: `runtime/hermes_adapter.py`, `runner/agents/{permissions,claude,codex,antigravity,base}.py`, `runner/backends/subprocess_backend.py`, `runtime/target_subdir.py`, `jobs/job_finalizer.py`, `jobs/job_launcher.py`, `main.py`, `runtime/planning/{contracts,validator}.py`, `runner/run-hermes-sprint.py`, and the earlier audit notes.
- Read-only inspection of `~/.gemini/antigravity-cli/settings.json` (matched by grep) and `~/hermes-worktrees`.
- Ran the test suite once (result above).
- Not run: git (per workspace rules), POST requests to localhost:8000, any agent.
