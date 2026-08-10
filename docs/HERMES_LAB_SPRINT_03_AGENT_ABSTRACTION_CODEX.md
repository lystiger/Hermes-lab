# Hermes Lab — Sprint 03
## Agent Abstraction + Codex Worker

**Sprint ID:** `lab-s03`
**Status:** Implemented
**Primary Implementer:** Claude Code
**Independent Reviewer:** Codex
**Optional Mechanical Worker:** Antigravity
**Supervisor / Operator:** Hermes
**Runtime UI:** Herdr

---

## 1. Sprint Goal

Refactor the current Hermes Lab sprint runner so that individual coding agents are implemented behind a common adapter interface, then add **Codex as a first-class third worker**.

Sprint 03 must preserve the deterministic controller model that already exists:

- the Python sprint runner owns orchestration;
- the controller owns Git operations;
- agents edit files only inside assigned worktrees;
- validation remains fail-fast;
- integration happens only through the controller;
- `READY_FOR_REVIEW` is granted only after all required phases and tests pass.

This sprint must **not** migrate execution to Herdr-managed panes yet.

That is reserved for Sprint 04.

---

# 2. Why This Sprint Exists

The current runner directly branches on agent identity:

```python
if agent == "antigravity":
    ...
elif agent == "claude":
    ...
else:
    raise SprintRunnerError("FAILED_UNKNOWN_AGENT", ...)
```

This works for two agents but does not scale.

Adding Codex directly with another `elif` would create increasing amounts of agent-specific orchestration logic inside the controller.

Sprint 03 replaces that pattern with an adapter layer.

Target architecture:

```text
Sprint Spec
    │
    ▼
HermesSprintRunner
    │
    ├── Agent Registry
    │     ├── AntigravityAdapter
    │     ├── ClaudeAdapter
    │     └── CodexAdapter
    │
    ├── Worktree Governance
    ├── Validation
    ├── Git Ownership
    ├── Integration
    └── Test Gate
```

The runner should understand **phases and contracts**, not CLI quirks.

---

# 3. Agent Responsibilities

## Claude Code — PRIMARY IMPLEMENTER

Claude owns the Sprint 03 implementation.

Responsibilities:

1. Refactor the current Antigravity and Claude execution logic into adapters.
2. Introduce the common agent interface.
3. Introduce an agent registry/factory.
4. Add the Codex adapter.
5. Update sprint execution so the controller dispatches through the registry.
6. Preserve current fail-fast behavior.
7. Preserve Antigravity's scoped permission handling.
8. Preserve Claude result validation.
9. Add or update unit tests for the adapter architecture.
10. Produce `HANDOFF_CLAUDE.md`.

Claude should perform the architectural refactor because the work spans:

- runner control flow;
- process execution;
- error handling;
- validation;
- configuration;
- tests;
- backwards compatibility.

---

## Codex — INDEPENDENT VERIFIER

Codex should review the integrated implementation after Claude.

Codex must not perform broad stylistic rewrites.

Responsibilities:

1. Inspect the adapter architecture.
2. Run the full test suite.
3. Look for regression risks.
4. Test invalid/unknown agents.
5. Test adapter command construction.
6. Test non-zero process exits.
7. Test malformed agent output.
8. Test missing adapters.
9. Test Codex execution behavior.
10. Add focused regression tests where coverage is missing.
11. Fix only defects supported by inspection or failing tests.
12. Produce `HANDOFF_CODEX.md`.

Codex should function as a verifier, not as a second architect.

---

## Antigravity — OPTIONAL SCAFFOLD WORKER

Antigravity may be used for mechanical work only.

Suitable tasks:

- create directory/file skeletons;
- move code with minimal semantic changes;
- create boilerplate tests;
- update simple configuration files.

Antigravity should not own the adapter architecture.

If parallel execution creates unnecessary coordination cost, skip Antigravity entirely for Sprint 03.

---

# 4. Target Repository Structure

Recommended structure:

```text
hermes-lab/
├── runner/
│   ├── run-hermes-sprint.py
│   │
│   └── agents/
│       ├── __init__.py
│       ├── base.py
│       ├── registry.py
│       ├── antigravity.py
│       ├── claude.py
│       └── codex.py
│
├── sprints/
│   └── lab-s03.json
│
├── prompts/
│   ├── s03-claude.md
│   └── s03-codex.md
│
└── tests/
    └── ...
```

Exact filenames may change if the existing test layout makes another structure cleaner.

Do not reorganize unrelated application code.

---

# 5. Common Agent Contract

Create a common interface for supported agents.

Conceptual API:

```python
class AgentAdapter:
    name: str

    def prepare(self, context):
        ...

    def build_command(self, prompt, options):
        ...

    def execute(self, context):
        ...

    def validate_result(self, result, context):
        ...

    def cleanup(self, context):
        ...
```

The exact implementation may use:

- an abstract base class;
- a protocol;
- a dataclass-based strategy;
- another small Python abstraction.

Prefer the smallest design that cleanly isolates agent-specific behavior.

Do **not** introduce a large framework.

---

# 6. Controller Responsibilities

The controller must continue to own:

```text
Sprint specification
        ↓
Worktree preparation
        ↓
Agent dispatch
        ↓
Changed-file validation
        ↓
Handoff validation
        ↓
Git stage
        ↓
Git commit
        ↓
Merge into integration
        ↓
Integration tests
        ↓
READY_FOR_REVIEW
```

Agent adapters must **not** own:

- `git add`
- `git commit`
- `git merge`
- `git rebase`
- integration branch mutation
- final sprint status

---

# 7. Adapter Responsibilities

Each adapter owns only agent-specific execution behavior.

Examples:

## AntigravityAdapter

Own:

- `agy` CLI command construction;
- output format flags;
- scoped Antigravity permissions;
- stream-JSON result validation;
- Antigravity-specific errors.

Preserve the existing permission model:

```text
worker worktree       → read/write
canonical .git        → read-only
worktree .git         → write denied
canonical .git        → write denied
```

The original Antigravity configuration must still be restored after:

- success;
- failure;
- timeout;
- exception.

---

## ClaudeAdapter

Own:

- `claude` CLI command construction;
- model;
- maximum turns;
- permission mode;
- JSON output;
- Claude result validation;
- permission-denial handling.

Do not weaken the existing validation rules.

---

## CodexAdapter

Own:

- Codex CLI command construction;
- non-interactive execution;
- prompt delivery;
- output capture;
- exit-code validation;
- Codex-specific validation;
- timeout behavior.

The adapter must use the installed Codex CLI rather than an API SDK.

The controller should be able to select Codex through the sprint spec:

```json
{
  "agent": "codex"
}
```

without additional controller branching.

---

# 8. Agent Registry

Introduce one mapping point for supported agents.

Conceptually:

```python
AGENT_REGISTRY = {
    "antigravity": AntigravityAdapter,
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
}
```

Controller dispatch should become conceptually:

```python
adapter = registry.get(agent_name)

if adapter is None:
    raise SprintRunnerError(
        "FAILED_UNKNOWN_AGENT",
        f"Unknown agent type: {agent_name}"
    )

adapter.execute(...)
```

There should be no growing chain of:

```python
if agent == ...
elif agent == ...
elif agent == ...
```

inside the main runner.

---

# 9. Sprint 03 Worktree Layout

Use a new sprint root.

```text
~/hermes-worktrees/hermes-lab-s03/
├── integration/
├── claude/
└── codex/
```

If Antigravity is used:

```text
~/hermes-worktrees/hermes-lab-s03/
├── integration/
├── antigravity/
├── claude/
└── codex/
```

Recommended branches:

```text
s03/integration
s03/claude
s03/codex
```

Optional:

```text
s03/antigravity
```

Do not reuse the Sprint 02 worktrees.

---

# 10. Recommended Sprint Flow

Preferred flow:

```text
main
  │
  ▼
s03/integration
  │
  ▼
Claude
adapter refactor
+ Codex support
  │
  ▼
controller validation
  │
  ▼
merge
  │
  ▼
Codex
independent review
+ regression tests
+ targeted fixes
  │
  ▼
controller validation
  │
  ▼
merge
  │
  ▼
isolated pytest
  │
  ▼
READY_FOR_REVIEW
```

This sprint does not need three implementation agents.

Quality of role separation is more important than number of agents.

---

# 11. Sprint Spec

Create `sprints/lab-s03.json`.

Recommended phases:

```json
{
  "sprint_id": "lab-s03",
  "name": "Agent Abstraction + Codex Worker",
  "canonical_repo": "/home/lystiger/hermes-lab",
  "base_branch": "main",
  "target_branch": "s03/integration",
  "worktree_root": "/home/lystiger/hermes-worktrees/hermes-lab-s03",
  "runs_root": "/home/lystiger/hermes-runs",
  "limits": {
    "max_changed_files": 20,
    "timeout_seconds": 600
  },
  "phases": [
    {
      "name": "agent_refactor",
      "agent": "claude",
      "worktree_dir": "claude",
      "branch": "s03/claude",
      "prompt_file": "prompts/s03-claude.md",
      "expected_handoff": "HANDOFF_CLAUDE.md",
      "commit_message": "refactor(s03): introduce agent adapter architecture"
    },
    {
      "name": "verification",
      "agent": "codex",
      "worktree_dir": "codex",
      "branch": "s03/codex",
      "prompt_file": "prompts/s03-codex.md",
      "expected_handoff": "HANDOFF_CODEX.md",
      "commit_message": "test(s03): verify agent adapters and codex integration"
    }
  ]
}
```

CLI-specific options should remain inside `cmd_options` where useful.

Do not hardcode model/provider configuration unnecessarily.

---

# 12. Required Tests

At minimum, add tests for:

### Registry

- known agent resolves;
- unknown agent fails with `FAILED_UNKNOWN_AGENT`;
- registry does not instantiate unsupported agents.

### Antigravity

- correct command generation;
- scoped permission install;
- permission restoration after success;
- permission restoration after exception;
- permission restoration after timeout;
- malformed/error output fails fast.

### Claude

- correct command generation;
- successful JSON result accepted;
- malformed JSON rejected;
- `is_error=true` rejected;
- permission denials rejected;
- non-zero process exit rejected.

### Codex

- correct Codex command generation;
- successful execution accepted;
- non-zero exit rejected;
- timeout rejected;
- missing executable surfaces a clear failure;
- output is persisted to run logs.

### Controller

- controller dispatches through registry;
- controller contains no agent-specific command construction;
- agent cannot bypass worktree validation;
- changed-file limit still applies;
- expected handoff still required;
- controller still owns commits;
- controller still owns merges;
- integration tests remain mandatory.

---

# 13. Backwards Compatibility

Existing Sprint 02 behavior must remain reproducible.

Refactoring must not intentionally change:

- Antigravity permissions;
- Claude permission mode behavior;
- worktree validation;
- dirty-repo protection;
- changed-file limits;
- handoff validation;
- Python syntax validation;
- run summary generation;
- isolated test environment;
- `READY_FOR_REVIEW` gate.

If behavior must change, document it explicitly in the handoff.

---

# 14. Logging

Preserve per-phase logs.

Example:

```text
<run_dir>/
├── agent_refactor_claude_stdout.log
├── agent_refactor_claude_stderr.log
├── verification_codex_stdout.log
├── verification_codex_stderr.log
├── runner.log
└── run_summary.json
```

The run summary should report:

```json
{
  "phase": "verification",
  "agent": "codex",
  "status": "SUCCESS"
}
```

in the same style as existing agents.

---

# 15. Non-Goals

Sprint 03 must **not**:

- replace the runner with Hermes;
- move orchestration into an LLM;
- migrate execution to Herdr panes;
- implement parallel agents;
- implement dynamic task planning;
- implement an agent message bus;
- implement remote execution;
- implement production deployment;
- redesign the FastAPI demo service;
- allow agents to commit or merge themselves.

These are deliberately outside scope.

---

# 16. Herdr Boundary

Herdr is installed and may be used interactively for observation during development.

However, Sprint 03 should retain:

```python
subprocess.run(...)
```

or the current equivalent execution mechanism behind the adapters.

The future target is:

```text
S03
Agent abstraction
        ↓
S04
Herdr execution backend
```

This ordering keeps two concerns separate:

```text
WHO executes
    ↓
AgentAdapter

HOW execution is hosted
    ↓
ExecutionBackend
```

Sprint 03 solves the first problem.

Sprint 04 will solve the second.

---

# 17. Future Sprint 04 Direction

Do not implement this yet.

Sprint 04 is expected to introduce an execution backend abstraction such as:

```text
ExecutionBackend
├── SubprocessBackend
└── HerdrBackend
```

Then:

```text
AgentAdapter
     │
     ▼
ExecutionBackend
     │
     ├── local subprocess
     └── persistent Herdr pane
```

This will allow:

```text
Antigravity
Claude
Codex
Hermes
```

to remain visible and resumable inside Herdr while preserving deterministic sprint governance.

---

# 18. Definition of Done

Sprint 03 is complete only when all of the following are true:

- [ ] Agent-specific code is extracted from the main controller.
- [ ] A common agent adapter contract exists.
- [ ] An agent registry exists.
- [ ] Antigravity runs through its adapter.
- [ ] Claude runs through its adapter.
- [ ] Codex runs through its adapter.
- [ ] Sprint specification can select `"agent": "codex"`.
- [ ] Unknown agents fail safely.
- [ ] Antigravity permission scoping still works.
- [ ] Claude validation still works.
- [ ] Codex result validation exists.
- [ ] Agent stdout/stderr remain logged.
- [ ] Worktree safety remains enforced.
- [ ] Agents cannot perform controller-owned Git operations.
- [ ] Claude produces `HANDOFF_CLAUDE.md`.
- [ ] Codex produces `HANDOFF_CODEX.md`.
- [ ] Full isolated pytest suite passes.
- [ ] Integration branch reaches `READY_FOR_REVIEW`.
- [ ] No Herdr execution migration is included.

---

# 19. Coding Ownership

Recommended ownership for this sprint:

```text
Claude Code
    │
    ├── adapter architecture
    ├── runner refactor
    ├── Antigravity adapter
    ├── Claude adapter
    ├── Codex adapter
    └── primary tests
           │
           ▼
        controller merge
           │
           ▼
Codex
    │
    ├── architecture review
    ├── regression tests
    ├── edge-case analysis
    └── targeted defect fixes
           │
           ▼
        controller merge
           │
           ▼
         pytest
```

### Why Claude should implement it

The risky portion of Sprint 03 is not writing the Codex command.

The risky portion is preserving every existing controller invariant while moving execution logic across several modules.

The primary implementer therefore needs to reason across:

- existing runner behavior;
- agent-specific validation;
- worktree lifecycle;
- error semantics;
- Git governance;
- tests.

Keep one architectural owner for that refactor.

### Why Codex should review it

Codex gives the sprint an independent implementation perspective.

Its job is to try to prove the refactor wrong through:

- tests;
- failure-path inspection;
- malformed input;
- process errors;
- boundary violations.

This is much more valuable than asking Codex to independently rewrite the same architecture.

---

# 20. Final Target After Sprint 03

```text
                     Hermes Lab

                        User
                         │
                         ▼
                      Hermes
               intelligent supervisor
                         │
                         ▼
                Python Sprint Runner
               deterministic controller
                         │
                 Agent Registry
             ┌───────────┼───────────┐
             ▼           ▼           ▼
           Agy         Claude       Codex
          Adapter      Adapter      Adapter
             │           │           │
             ▼           ▼           ▼
          Worktree     Worktree    Worktree
             │           │           │
             └───────────┼───────────┘
                         ▼
                  Integration Branch
                         │
                         ▼
                       Pytest
                         │
                         ▼
                 READY_FOR_REVIEW

Herdr:
runtime visibility and agent session management today;
execution backend in Sprint 04.
```

---

## Sprint Principle

> **LLMs may reason and write code. The controller owns state, policy, Git, validation, and promotion.**
