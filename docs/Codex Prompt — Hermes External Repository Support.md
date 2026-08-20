# Task: Make Hermes Work Against External Repositories on WSL and Windows

You are modifying:

```text
lystiger/Hermes-lab
```

## Objective

Refactor Hermes so that the repository containing the Hermes controller, prompts, sprint specifications, and runtime code is **not required to be the repository being modified by agents**.

Hermes must be able to orchestrate work against an arbitrary local Git repository.

Target usage must work on:

- Linux
- WSL
- native Windows

Do **not** redesign Hermes.

Do **not** implement LysStack integration yet.

Do **not** generalize verification commands yet.

Do **not** add OMP.

Do **not** change the Builder/Hardener/Verifier workflow yet.

This task is only about **external target repository support and path portability**.

---

# Current Problem

The runner currently conflates two different concepts:

```text
Hermes repository
=
target repository
```

For example, `canonical_repo` is currently used for:

1. Git/worktree operations.
2. Canonical repository cleanliness checks.
3. Resolving prompt files.
4. Report paths.
5. Other Hermes-owned files.

This prevents a configuration such as:

```text
Hermes:
C:\Users\me\projects\Hermes-lab

Target:
C:\Users\me\projects\Unigreen
```

or under WSL:

```text
Hermes:
/home/user/projects/Hermes-lab

Target:
/home/user/projects/Unigreen
```

because changing `canonical_repo` to Unigreen would cause Hermes to incorrectly search for Hermes-owned prompt files inside Unigreen.

---

# Required Architectural Boundary

After this change, distinguish these concepts explicitly:

```text
control_root
    Hermes-lab repository

target_repo
    repository whose source code the agents modify

worktree_root
    location where target-repository worktrees are created

runs_root
    Hermes runtime logs/evidence
```

Conceptually:

```text
Hermes-lab
├── runner/
├── prompts/
├── sprints/
└── reports/

          controls

Unigreen
├── backend/
├── frontend/
└── ...

          modified through

Hermes worktrees
├── integration/
├── antigravity/
├── claude/
└── codex/
```

The target repository must contain **no Hermes runtime implementation files**.

---

# Configuration Contract

Introduce an explicit target repository field in sprint specifications.

Preferred shape:

```json
{
  "sprint_id": "external-example",

  "target_repo": "/path/to/project",

  "base_ref": "main",
  "target_branch": "hermes/external-example",

  "worktree_root": "/path/to/hermes-worktrees/external-example",
  "runs_root": "/path/to/hermes-runs",

  "phases": []
}
```

The Hermes repository itself should normally be derived from the location of the running Hermes code/spec rather than requiring users to duplicate an absolute `control_root`.

If an explicit `control_root` is useful for testing or portability, it may be supported, but avoid unnecessary configuration.

The important invariant is:

```text
prompt_file -> resolved relative to Hermes/control root

Git operations -> target_repo

worktrees -> worktrees belonging to target_repo
```

---

# Backward Compatibility

Existing Hermes sprint specifications such as:

```text
lab-s02
lab-s03
lab-s04
lab-s05
lab-s06
```

must continue to work.

Existing specs currently use:

```json
"canonical_repo": "/home/lystiger/hermes-lab"
```

Do not break those specs unnecessarily.

A reasonable compatibility strategy is:

```text
target_repo
    if explicitly supplied

otherwise:

legacy canonical_repo
    if supplied

otherwise:

Hermes control root
```

However, do not preserve confusing semantics internally merely for compatibility.

Normalize legacy configuration into the new internal model during loading.

Example internal state:

```python
self.control_root
self.target_repo
self.worktree_root
self.runs_root
```

Avoid continuing to use one ambiguous `canonical_repo` variable everywhere.

---

# Required Behavior

## 1. Hermes-owned files

The following must resolve from the Hermes repository/control root:

```text
prompts/
sprints/
runner/
reports/
```

Example:

```python
prompt_file = control_root / phase["prompt_file"]
```

NOT:

```python
prompt_file = target_repo / phase["prompt_file"]
```

---

## 2. Git operations

All product/source Git operations must target:

```text
target_repo
```

including:

```text
git status
git branch
git worktree add
git merge-related repository operations
```

Agent worktrees must be worktrees of the target repository.

---

## 3. Cleanliness protection

Before execution, Hermes must verify that the **target repository** is clean.

Do not accidentally validate only Hermes-lab when the target is another project.

If Hermes itself also requires a cleanliness check for some operation, make that a separate explicit concern.

Do not conflate the two repositories.

---

## 4. Worktrees

Given:

```text
target_repo = Unigreen
```

Hermes should create something equivalent to:

```text
<worktree_root>/
├── integration
├── antigravity
├── claude
└── codex
```

and all of those must correspond to branches in **Unigreen**, not Hermes-lab.

---

# Cross-Platform Requirement

This implementation must be portable between:

```text
Linux
WSL
Windows
```

Do not implement Windows support through hard-coded string replacement.

Use Python filesystem abstractions properly.

Prefer:

```python
pathlib.Path
```

over manually joining paths with:

```text
/
\
```

Do not assume:

```text
/home/lystiger/...
```

Do not assume:

```text
C:\...
```

Do not concatenate filesystem paths manually when `Path` can represent them.

---

# WSL Requirements

A normal WSL configuration should work:

```json
{
  "target_repo": "/home/user/projects/Unigreen",
  "worktree_root": "/home/user/hermes-worktrees/unigreen"
}
```

A repository mounted from Windows may also be represented as:

```text
/mnt/c/Users/user/projects/Unigreen
```

Hermes should treat this as a normal filesystem path.

Do not add WSL-specific conversion logic unless the existing implementation demonstrably requires it.

---

# Native Windows Requirements

A native Windows configuration should be possible:

```json
{
  "target_repo": "C:\\Users\\user\\projects\\Unigreen",
  "worktree_root": "C:\\Users\\user\\hermes-worktrees\\unigreen",
  "runs_root": "C:\\Users\\user\\hermes-runs"
}
```

Python should resolve these correctly when Hermes itself is running under Windows.

Do not attempt to make a Linux Python process interpret `C:\...` as a local Windows path.

The supported rule is:

```text
WSL Hermes → use WSL-visible paths
Windows Hermes → use Windows paths
Linux Hermes → use Linux paths
```

This task requires platform portability, not magical cross-kernel path translation.

---

# Avoid Shell-Specific Assumptions

Inspect the changed execution path for assumptions such as:

```text
/bin/bash
/bin/sh
which
chmod
HOME=/home/...
```

Do not rewrite unrelated execution backends in this task.

However, any code directly introduced or modified for external repository support must not rely unnecessarily on POSIX-only shell behavior.

Git commands should continue to use argv arrays, e.g.:

```python
["git", "status", "--porcelain"]
```

rather than shell strings.

---

# Spec Path Resolution

Be precise about relative paths.

Recommended rules:

### `prompt_file`

Relative to:

```text
Hermes control root
```

### `target_repo`

If absolute:

```text
use directly
```

If relative paths are supported, define exactly what they are relative to.

Preferred choice:

```text
relative to the sprint specification directory
```

or:

```text
relative to control_root
```

Pick one deterministic rule, document it, and test it.

Do not resolve relative paths based on the user's current shell working directory.

The same invocation should behave identically regardless of where the command is launched from.

---

# Report Location

Existing sanitized report behavior must remain valid.

If the report path is Hermes-owned, it should not silently become:

```text
Unigreen/reports/...
```

just because Unigreen is the target.

Default Hermes execution evidence should stay associated with Hermes/runtime storage.

Do not pollute the target project with Hermes reports.

---

# Existing Behavior That Must Remain

Do not regress:

- dirty repository protection
- worktree validation
- wrong-branch detection
- dirty-worktree detection
- reset-to-configured-base behavior
- isolated integration branch
- agent branch/worktree creation
- phase synchronization
- controller-owned Git mutations
- no remote push
- no merge to target `main`
- existing execution backend selection
- existing agent adapters
- sanitized report export

---

# Tests Required

Add focused automated tests.

Do not rely only on manual testing.

At minimum cover:

## A. External repository separation

Create temporary Git repositories representing:

```text
Hermes control repo
Target repo
```

Verify:

```text
prompt resolution uses control repo

git/worktree operations use target repo
```

The test should fail if Hermes accidentally creates agent branches in the control repository.

---

## B. Legacy spec compatibility

Load an existing-style specification using:

```json
{
  "canonical_repo": "..."
}
```

and verify it still normalizes correctly.

---

## C. Explicit `target_repo`

Verify:

```json
{
  "target_repo": "..."
}
```

takes precedence over legacy `canonical_repo` semantics where appropriate.

---

## D. Paths with spaces

Test paths such as:

```text
/tmp/Hermes Project
/tmp/Uni Green Project
```

or the platform-appropriate equivalent.

No command should break because a repository path contains spaces.

---

## E. Windows path handling

Tests should not require a Windows machine just to run the Linux test suite.

Separate:

1. filesystem-independent configuration/path parsing tests
2. actual filesystem integration tests

Use appropriate abstractions such as `PureWindowsPath` where useful for logic that does not require filesystem access.

Do not write a fake test that passes a Windows path into POSIX `Path.resolve()` and then claims native Windows support.

The implementation should rely on standard Python path behavior on the platform where Hermes runs.

---

## F. Relative spec invocation

If relative target paths are supported, verify launching Hermes from different current working directories resolves the same target.

---

# Important Non-Goals

Do NOT include these in this patch:

- generic verification commands
- `uv` support
- Unigreen-specific logic
- LysStack integration
- `context_root`
- role abstraction
- Builder/Hardener/Verifier rename
- `allow_no_changes`
- verifier read-only mode
- handoff relocation
- OMP
- session/RPC redesign
- dashboard/UI
- GitHub push or PR creation
- deployment

Those will be handled separately.

---

# Naming

Prefer precise names.

Good:

```python
control_root
target_repo
worktree_root
runs_root
spec_path
```

Avoid introducing more ambiguous names such as:

```python
repo
main_repo
project_dir
root
canonical
```

unless their meaning is extremely clear.

---

# Expected Example After Implementation

The following should become possible.

Hermes located at:

```text
/home/user/Hermes-lab
```

Target repository:

```text
/home/user/projects/Unigreen
```

Sprint spec stored at:

```text
/home/user/Hermes-lab/sprints/unigreen-test.json
```

with:

```json
{
  "sprint_id": "unigreen-test",
  "target_repo": "/home/user/projects/Unigreen",
  "base_ref": "main",
  "target_branch": "hermes/unigreen-test",
  "worktree_root": "/home/user/hermes-worktrees/unigreen-test",
  "runs_root": "/home/user/hermes-runs",
  "phases": [
    {
      "name": "scaffold",
      "agent": "antigravity",
      "worktree_dir": "antigravity",
      "branch": "hermes/unigreen-test-agy",
      "prompt_file": "prompts/example.md",
      "expected_handoff": "HANDOFF_AGY.md",
      "commit_message": "test: external repository execution"
    }
  ]
}
```

Hermes must then:

```text
read prompt:
    Hermes-lab/prompts/example.md

check cleanliness:
    projects/Unigreen

create Git branches:
    in Unigreen

create worktrees:
    from Unigreen

execute agent:
    inside Unigreen worktree

write runtime logs:
    hermes-runs/...

never modify:
    Hermes-lab source repository
    except explicitly requested Hermes-owned runtime/report paths
```

---

# Documentation

Update the relevant Hermes documentation with a short section explaining:

```text
Hermes control repository vs target repository
```

Include examples for:

### WSL/Linux

```json
"target_repo": "/home/user/projects/Unigreen"
```

### WSL accessing Windows filesystem

```json
"target_repo": "/mnt/c/Users/user/projects/Unigreen"
```

### native Windows

```json
"target_repo": "C:\\Users\\user\\projects\\Unigreen"
```

Explicitly state:

```text
Use paths native to the environment where Hermes Python is running.
```

---

# Implementation Quality

Keep the patch surgical.

Do not build an abstraction framework unless needed.

Prefer:

```text
small normalization layer
+
explicit internal paths
+
existing runner behavior
```

over a large configuration subsystem.

Preserve testability.

Avoid hidden fallback behavior.

Invalid repository configuration should fail early with a clear Hermes error.

Examples:

```text
FAILED_TARGET_REPO_MISSING
FAILED_TARGET_REPO_NOT_GIT
```

if adding such failure states cleanly fits the existing error model.

---

# Verification

Run the full Hermes test suite.

At minimum:

```bash
python -m pytest -v
```

Also run any repository-standard checks already documented by Hermes.

Report:

1. files changed
2. architectural changes
3. backward-compatibility behavior
4. tests added
5. exact verification results
6. any remaining platform limitations

---

# Definition of Done

This task is complete only when:

- [ ] Hermes distinguishes its own control repository from the target repository.
- [ ] `target_repo` can point to another local Git repository.
- [ ] prompts continue to resolve from Hermes.
- [ ] Git/worktree operations occur against the target repository.
- [ ] existing Hermes-only sprint specs still work.
- [ ] path handling contains no new Linux-only assumptions.
- [ ] WSL paths work naturally.
- [ ] native Windows paths are supported when running under Windows.
- [ ] paths containing spaces are tested.
- [ ] target repository misconfiguration fails clearly.
- [ ] tests prove control/target separation.
- [ ] documentation explains Linux, WSL, and Windows usage.
- [ ] no Unigreen-specific behavior is introduced.

Stop when these requirements are satisfied.

Do not continue into verification generalization or LysStack integration.