# Security Audit: Agent Permission Skipping and Execution Containment

**Date:** 2026-11-06  
**Auditor:** Hermes Security Auditor (Builder Role)  
**Target:** Hermes Agent Permission Mechanisms & Guardrails  
**Scope:** `antigravity_skip_permissions` propagation, agent CLI flags, and containment boundaries (sandbox mode, trustedWorkspaces, deny lists, worktree cwd) across Antigravity, Claude, and Codex.

---

## 1. Executive Summary

Hermes supports three primary agent adapters: **Antigravity** (`agy`), **Claude** (`claude`), and **Codex** (`codex`).
- **Antigravity:** Can be explicitly instructed via API/job metadata (`antigravity_skip_permissions: True`) to execute with `--dangerously-skip-permissions`. In this mode, Antigravity has **zero sandbox isolation**, bypasses all `settings.json` allow/deny rules and `trustedWorkspaces`, and runs arbitrary shell commands with full user privileges. Furthermore, the permission scoping mechanism (`scoped_antigravity_permissions`) introduces a concurrency race condition by mutating the global user file `~/.gemini/antigravity-cli/settings.json`.
- **Claude:** Does not use `antigravity_skip_permissions`, but **by default always runs with `--permission-mode dontAsk`** without an OS sandbox. The only bound is a command blacklist (`CLAUDE_GIT_MUTATION_DENIALS`) passed to `--disallowedTools`, which matches tool input prefixes and can be trivially bypassed via scripts or wrapper commands.
- **Codex:** Immune to skip-permission flags. It strictly hardcodes `--sandbox workspace-write` and `--cd <worktree>` in its adapter, preventing worker tasks from relaxing the sandbox boundary.

---

## 2. Tracing `antigravity_skip_permissions` and Agent Flags

### 2.1 HTTP API Ingestion
- **File & Lines:** [main.py:534](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/main.py#L534), [main.py:570](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/main.py#L570)
- **Evidence:**
  `CreateGoalJobPayload` defines the field:
  ```python
  # main.py:534
  antigravitySkipPermissions: bool = False
  ```
  In route `POST /jobs/goal`:
  ```python
  # main.py:570
  antigravity_skip_permissions=payload.antigravitySkipPermissions,
  ```
  The boolean is forwarded directly to `job_launcher.launch_goal_background(...)`.

### 2.2 Job Orchestration & Adapter Configuration
- **File & Lines:** [jobs/job_launcher.py:507-511](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/jobs/job_launcher.py#L507-L511), [jobs/job_launcher.py:562](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/jobs/job_launcher.py#L562), [jobs/job_launcher.py:604](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/jobs/job_launcher.py#L604), [jobs/job_launcher.py:916-918](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/jobs/job_launcher.py#L916-L918)
- **Evidence:**
  `launch_goal` accepts the parameter:
  ```python
  # jobs/job_launcher.py:562
  antigravity_skip_permissions: bool = False,
  ```
  And stores it in job metadata:
  ```python
  # jobs/job_launcher.py:604
  "antigravity_skip_permissions": antigravity_skip_permissions,
  ```
  When constructing execution adapters in `_goal_adapters`:
  ```python
  # jobs/job_launcher.py:507-511
  default_agent_options={
      **({"max_turns": agent_max_turns} if agent_max_turns else {}),
      **({"dangerously_skip_permissions": True} if meta.get("antigravity_skip_permissions") else {}),
  } or None,
  ```
  The option `dangerously_skip_permissions: True` is placed in `default_agent_options` and passed to `HermesActorAdapter`.
  On resume (`resume_async`, line 916), `_goal_adapters` reads `meta["antigravity_skip_permissions"]` from the persistent event store, ensuring resumed jobs retain the skip-permissions flag.

  *(Note: In legacy or sprint-spec jobs launched via `launch()`, lines 306–320 and 337–350 do not set `default_agent_options` globally; options are sourced per phase from `cmd_options`.)*

### 2.3 Task Dispatch and Context Assembly
- **File & Lines:** [runtime/hermes_adapter.py:233](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runtime/hermes_adapter.py#L233), [runtime/hermes_adapter.py:241](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runtime/hermes_adapter.py#L241), [runtime/hermes_adapter.py:1327](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runtime/hermes_adapter.py#L1327), [runtime/hermes_adapter.py:1340](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runtime/hermes_adapter.py#L1340)
- **Evidence:**
  `HermesActorAdapter.__init__` stores `self.default_agent_options = default_agent_options or {}`.
  When executing a task in `_execute_real_agent`:
  ```python
  # runtime/hermes_adapter.py:1327, 1340
  options={**self.default_agent_options, **task.metadata.get("options", {})},
  ```
  `AgentContext` receives `options` with `dangerously_skip_permissions: True`, which is dispatched to `agent_adapter.execute(agent_ctx)` (line 1348).

---

## 3. Detailed Agent Containment Analysis

### 3.1 Antigravity (`runner/agents/antigravity.py`)

#### Command Line Generation
- **File & Lines:** [runner/agents/antigravity.py:15-32](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/antigravity.py#L15-L32)
- **Evidence:**
  ```python
  # runner/agents/antigravity.py:30-31
  if options.get("dangerously_skip_permissions", False):
      command.append("--dangerously-skip-permissions")
  ```
  When the flag is active, `agy` is called with:
  `agy --new-project -p <prompt> --output-format stream-json --dangerously-skip-permissions`

#### Permissions Scoping & Concurrency Flaw
- **File & Lines:** [runner/agents/antigravity.py:40-48](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/antigravity.py#L40-L48), [runner/agents/permissions.py:7-75](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/permissions.py#L7-L75)
- **Evidence:**
  Even when `dangerously_skip_permissions` is set, `AntigravityAdapter.execute()` invokes `scoped_antigravity_permissions`:
  ```python
  # runner/agents/antigravity.py:41-48
  permissions = context.phase.get("permissions", {})
  with scoped_antigravity_permissions(
      context.worktree,
      context.runner.target_repo,
      settings_path=self.settings_path,
      allowed_commands=permissions.get("commands", ()),
  ):
      return super().execute(context)
  ```
  `scoped_antigravity_permissions` attempts to restrict permissions by writing to `~/.gemini/antigravity-cli/settings.json`:
  1. `trustedWorkspaces`: appends `str(wt_dir.resolve())` (line 45).
  2. `allow` rules: read/write on worktree, read on `.git` in canonical repo, plus `pwd`, `ls -la`, `pwd && ls -la`, `python3 -m pytest -q`, and `allowed_commands` (lines 47-59).
  3. `deny` rules: `write_file` to `.git` in worktree and canonical repo (lines 60-65).
  4. Cleanup: in `finally:` (line 78), it overwrites `settings.json` with the original bytes captured at entry.

#### Containment Boundaries When Flag Is ON:
1. **Sandbox mode:** **NONE**. Neither the CLI nor `SubprocessBackend` (`runner/backends/subprocess_backend.py:28-29, 95-101`) applies containerization (no Docker, bubblewrap, seccomp, or namespaces).
2. **trustedWorkspaces:** **INEFFECTIVE**. The CLI flag `--dangerously-skip-permissions` disables CLI permission prompts and boundary checks regardless of workspace trust status.
3. **deny lists:** **BYPASSED**. The deny rules configured in `settings.json` (such as blocking writes to `.git`) are bypassed by `--dangerously-skip-permissions`.
4. **worktree cwd:** **UNCONFINED**. While `subprocess.Popen` sets `cwd=context.worktree`, the agent process has standard user privileges and full shell access. It can execute `rm -rf`, read `~/.ssh`, exfiltrate secrets, or alter any accessible filesystem paths.
5. **Global concurrency race:** Because `scoped_antigravity_permissions` mutates a single global file (`~/.gemini/antigravity-cli/settings.json`) without file-locking, concurrent tasks will clobber each other's settings or prematurely revert permissions upon completion.

---

### 3.2 Claude (`runner/agents/claude.py`)

#### Command Line Generation
- **File & Lines:** [runner/agents/claude.py:57-88](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/claude.py#L57-L88)
- **Evidence:**
  Claude does **not** consume `antigravity_skip_permissions`. Instead, its permission mode is hardcoded to default to `dontAsk`:
  ```python
  # runner/agents/claude.py:74-75
  "--permission-mode",
  options.get("permission_mode", "dontAsk"),
  ```
  Tool allowlist defaults to:
  ```python
  # runner/agents/claude.py:59, 78-79
  allowed_tools = options.get("allowed_tools", ["Bash", "Edit", "Write", "Skill"])
  ...
  "--allowedTools", ",".join(dict.fromkeys(allowed_tools)),
  ```
  Tool denylist adds Git mutations:
  ```python
  # runner/agents/claude.py:65-67, 80-81
  disallowed_tools = tuple(
      dict.fromkeys((*CLAUDE_GIT_MUTATION_DENIALS, *extra_denials))
  )
  ...
  "--disallowedTools", ",".join(disallowed_tools),
  ```

#### Containment Boundaries:
1. **Sandbox mode:** **NONE**. Claude runs as a direct unconfined subprocess.
2. **trustedWorkspaces:** **NOT APPLICABLE**.
3. **deny lists:** **PARTIAL / EASILY BYPASSED**. `CLAUDE_GIT_MUTATION_DENIALS` (`runner/agents/claude.py:8-51`) denies direct invocations of git mutating subcommands through the Claude `Bash` tool (e.g., `Bash(git commit)`, `Bash(git push)`). However, Claude CLI tool restrictions match command string prefixes; an agent can easily bypass this by writing a wrapper script (e.g. `sh -c 'git commit'` or executing a python script that runs git).
4. **worktree cwd:** **UNCONFINED**. Process starts in `context.worktree`, but arbitrary commands run via the `Bash` tool can access files outside the worktree, environment variables, and network resources.
5. **Default posture:** Claude operates with skip-permissions (`--permission-mode dontAsk`) on every run by default.

---

### 3.3 Codex (`runner/agents/codex.py`)

#### Command Line Generation
- **File & Lines:** [runner/agents/codex.py:13-27](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/codex.py#L13-L27)
- **Evidence:**
  ```python
  # runner/agents/codex.py:15-26
  command = ["codex", "exec", "--color", "never"]
  if worktree is not None:
      command.extend(["--cd", str(worktree)])
  if options.get("model"):
      command.extend(["--model", str(options["model"])])
  if options.get("effort"):
      command.extend(["-c", "model_reasoning_effort=" + json.dumps(options["effort"])])
  # Worker specs cannot weaken the workspace boundary.
  command.extend(["--sandbox", "workspace-write"])
  if options.get("ephemeral", True):
      command.append("--ephemeral")
  ```

#### Containment Boundaries:
1. **Sandbox mode:** **ENFORCED**. Codex hardcodes `--sandbox workspace-write`. The Codex CLI sandbox confines file write operations to the designated workspace.
2. **trustedWorkspaces:** **MANAGED BY CODEX**.
3. **deny lists:** **ENFORCED BY CODEX SANDBOX**.
4. **worktree cwd:** **CONFINED**. Explicitly passed via `--cd <worktree>`.
5. **Inviolability:** Unlike Antigravity and Claude, Codex has **no skip-permissions flag** and explicitly disallows relaxing the sandbox boundary (`# Worker specs cannot weaken the workspace boundary.`).

---

## 4. Post-Execution Denial Auditing Blindspot

- **File & Lines:** [runner/agents/denials.py:27-54](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_211008_22b99994/audit_skip_permissions/runner/agents/denials.py#L27-L54)
- **Evidence:**
  `check_denials` inspects permission denials emitted by agents during execution:
  ```python
  # runner/agents/denials.py:51-53
  if texts and (scope or not usable or len(texts) > int(options.get("permission_denial_ceiling", 20))
                or strict):
      raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Permission denials ({len(texts)}): {texts}")
  ```
- **Vulnerability:**
  `check_denials` is purely reactive: it only checks `texts` extracted from reported denial events or stderr messages. When an agent runs with `--dangerously-skip-permissions` (Antigravity) or `--permission-mode dontAsk` (Claude), the CLI **never raises a permission denial**.
  Consequently, `texts` is empty (`[]`), and `check_denials` passes silently even if the agent accessed or modified resources completely outside its worktree or violated Git boundaries.

---

## 5. Risk Assessment & Smallest Proposed Guardrails

| Risk Description | Likelihood | Impact | Current Bound | Proposed Smallest Guardrail |
| :--- | :--- | :--- | :--- | :--- |
| **Antigravity Unconfined Execution:** `antigravity_skip_permissions=True` disables all boundary checks; agent runs as user with arbitrary shell access. | High (when flag used) | Critical | Only process timeout. | Run `agy` inside an OS-level sandbox (e.g. `bwrap --ro-bind / / --bind <worktree> <worktree>`) or restrict network/filesystem access. |
| **Claude Default `dontAsk` Execution:** Claude runs with `--permission-mode dontAsk` by default, giving arbitrary shell execution via `Bash` tool. | High | High | String prefix match on `--disallowedTools`. | Wrap agent execution in a restricted environment or require `--sandbox` equivalent for Claude bash operations. |
| **Concurrent Mutation of `settings.json`:** `scoped_antigravity_permissions` mutates shared `~/.gemini/antigravity-cli/settings.json` without file locking. | Medium | Medium | In-memory Python context manager only. | Pass isolated configuration via `settings_path` or environment variable per task, avoiding mutations to user home. |
| **Git Mutation Deny List Bypass in Claude:** Disallow rules match direct `Bash(git <subcommand>)`, bypassed by shell scripts or python. | Medium | High | Tool prefix match in Claude CLI. | Place a pre-exec hook or filesystem read-only mount on `.git` directory so underlying OS rejects git mutations regardless of caller method. |
| **Post-Execution Denial Blindspot:** `check_denials` is inert when permission checks are skipped because no denial messages are generated. | High | Medium | None when skip-permissions active. | Verify repository state and worktree boundary via `git status` / filesystem diff inspection after task execution rather than relying on agent self-reported denials. |
