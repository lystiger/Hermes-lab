# Hermes Lab — Sprint 04
## Execution Backend Abstraction + Herdr Runtime

**Sprint ID:** `lab-s04`
**Baseline:** Sprint 03.1 frozen after Claude CLI permission-rule correction
**Primary Implementer:** Claude Code
**Independent Reviewer:** Codex
**Runtime Target:** Herdr
**Existing Reference Backend:** Local subprocess
**Supervisor / Operator:** Hermes

---

# 1. Sprint Goal

Introduce an execution-backend boundary underneath the existing agent adapters, then add a **Herdr-backed execution mode** without removing or weakening the current subprocess execution path.

Sprint 04 must preserve the controller architecture established in Sprint 03:

```text
                      Sprint Controller
                             │
                      Agent Registry
                             │
                  ┌──────────┴──────────┐
                  │                     │
             AgentAdapter         ExecutionBackend
                  │                 /          \
                  │                /            \
                  └───────────────┼──────────────┘
                                  │
                         ┌────────┴────────┐
                         │                 │
                  SubprocessBackend   HerdrBackend
```

The controller continues to own:

- sprint sequencing;
- deterministic worktree initialization;
- Git staging;
- Git commits;
- Git merges;
- changed-file validation;
- handoff validation;
- syntax validation;
- integration tests;
- final promotion to `READY_FOR_REVIEW`;
- sanitized evidence export.

The execution backend owns only **how an agent process is hosted and observed**.

---

# 2. Important Scope Decision

Sprint 04 should **not immediately convert the workers to Herdr's interactive `agent start` + `agent prompt` model**.

The current adapters depend on deterministic non-interactive CLI result contracts:

```text
Antigravity → stream-json
Claude      → JSON result
Codex       → codex exec stdout/exit code
```

An interactive Herdr agent session exposes lifecycle state and terminal output rather than the exact machine-readable result contract currently validated by the adapters.

Replacing both:

```text
process hosting
AND
agent result semantics
```

in the same sprint would make failures difficult to attribute.

Therefore Sprint 04 uses Herdr primarily as the **process-hosting/runtime layer**, while preserving the existing one-shot agent CLI invocation and validation contracts.

Target evolution:

```text
Sprint 03
AgentAdapter
    │
    └── subprocess.run()

Sprint 04
AgentAdapter
    │
    ▼
ExecutionBackend
    ├── SubprocessBackend
    └── HerdrBackend
           │
           └── persistent Herdr pane hosts the same one-shot CLI

Future sprint
Herdr interactive/sessionful agent execution
    └── agent start / agent prompt / resume
```

This keeps Sprint 04 narrow and testable.

---

# 3. Current Invariants That Must Survive

Do not weaken any Sprint 03/S03.1 guardrail.

The following remain mandatory:

```text
FAILED_DIRTY_REPO
FAILED_INVALID_WORKTREE
FAILED_WRONG_BRANCH
FAILED_DIRTY_WORKTREE
FAILED_TIMEOUT
FAILED_PERMISSION_DENIED
FAILED_UNKNOWN_AGENT
FAILED_AGENT_EXECUTABLE_MISSING
FAILED_AGENT_EXECUTION
FAILED_NO_CHANGES
FAILED_EXCESSIVE_FILES
FAILED_MISSING_HANDOFF
FAILED_SYNTAX_ERROR
FAILED_TESTS
```

Also preserve:

- deterministic worktree resets;
- later-phase synchronization from integration;
- Antigravity temporary permission restoration;
- Claude Git-mutation denials;
- Codex `workspace-write` enforcement;
- isolated pytest;
- sanitized run report;
- controller-only Git mutation.

---

# 4. New Execution Backend Contract

Add a backend package.

Recommended structure:

```text
runner/
├── run-hermes-sprint.py
│
├── agents/
│   ├── base.py
│   ├── registry.py
│   ├── antigravity.py
│   ├── claude.py
│   └── codex.py
│
└── backends/
    ├── __init__.py
    ├── base.py
    ├── subprocess_backend.py
    └── herdr_backend.py
```

Use the smallest abstraction that works.

Recommended conceptual contract:

```python
@dataclass(frozen=True)
class ExecutionRequest:
    agent_name: str
    command: list[str]
    cwd: Path
    timeout_seconds: int
    stdout_file: Path
    stderr_file: Path
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ExecutionResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    backend: str
    runtime_metadata: Mapping[str, Any]


class ExecutionBackend(ABC):
    name: str

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...
```

Exact names may change.

Do not introduce a framework or plugin system.

---

# 5. Adapter / Backend Boundary

Agent adapters continue to own:

```text
what command should be executed
how agent-specific output should be validated
agent-specific temporary preparation/cleanup
```

Execution backends own:

```text
where the process runs
how stdout/stderr are collected
how timeout is enforced
how process completion is detected
runtime-specific metadata
```

Conceptually:

```python
command = adapter.build_command(...)

result = backend.execute(
    ExecutionRequest(
        agent_name=adapter.name,
        command=command,
        cwd=context.worktree,
        ...
    )
)

adapter.validate_result(result, context)
```

The adapter must not know whether the command ran through:

```text
subprocess.run
```

or:

```text
a Herdr pane
```

---

# 6. SubprocessBackend

Move the current process execution behavior into `SubprocessBackend`.

It should remain the reference implementation.

Behavior must remain equivalent to current Sprint 03:

```python
subprocess.run(
    command,
    cwd=worktree,
    capture_output=True,
    text=True,
    timeout=...
)
```

Preserve:

- stdout;
- stderr;
- exit code;
- timeout behavior;
- missing executable behavior;
- permission-denied behavior;
- per-phase logs.

A Sprint 03 spec executed through `SubprocessBackend` should behave the same as before this refactor.

---

# 7. HerdrBackend — Sprint 04 Version

The first Herdr backend should host the existing one-shot command inside a **persistent Herdr terminal pane**.

Do not change the adapter output contract yet.

## 7.1 Preflight

Before executing a phase, verify:

```text
herdr executable is installed
Herdr server is reachable
required worker executable is installed
```

Recommended failures:

```text
FAILED_HERDR_EXECUTABLE_MISSING
FAILED_HERDR_UNAVAILABLE
FAILED_HERDR_COMMAND
FAILED_HERDR_PROTOCOL
```

Do not silently fall back to subprocess when the user explicitly selected Herdr.

Silent fallback makes experiments impossible to trust.

Fallback should be explicit through configuration.

---

## 7.2 Workspace Strategy

Prefer one Herdr workspace for the sprint run:

```text
Hermes Lab — lab-s04
│
├── controller
├── claude
└── codex
```

or equivalent tabs/panes.

The backend must **consume IDs returned by Herdr's JSON output**.

Never predict IDs such as:

```text
w1:p2
w1:p3
```

Store runtime identifiers in memory:

```json
{
  "workspace_id": "...",
  "pane_id": "...",
  "agent": "claude"
}
```

They may appear in the local run summary/runtime logs, but should not be placed in sanitized evidence if they are unnecessary or machine-specific.

---

## 7.3 Pane Creation

For a worker phase:

1. create or reuse the sprint workspace;
2. create a pane whose `cwd` is the worker worktree;
3. give it a readable label where practical;
4. keep the pane alive after command completion;
5. do not steal focus from the user.

Example conceptual flow:

```text
herdr workspace create
        │
        ▼
capture root pane ID
        │
        ▼
herdr pane split/create
        │
        ▼
worker pane
```

Do not couple controller correctness to UI layout geometry.

A pane ID is runtime identity.

Whether it appears right/down is presentation only.

---

# 8. Running the Existing CLI in Herdr

Sprint 04 HerdrBackend should execute the command generated by the adapter rather than replacing it with interactive prompting.

For example, Claude should still effectively execute the equivalent of:

```text
claude -p <prompt> ... --output-format json
```

Codex should still effectively execute:

```text
codex exec ... --sandbox workspace-write --ephemeral <prompt>
```

The backend should use a shell wrapper that:

1. runs the exact argv safely;
2. captures stdout to the controller-owned stdout log;
3. captures stderr to the controller-owned stderr log;
4. captures the exit code;
5. emits a unique completion sentinel;
6. leaves the pane at a shell prompt afterward.

Conceptual runtime:

```text
Herdr pane
    │
    ├── worker CLI
    │     ├── stdout → run log
    │     └── stderr → run log
    │
    ├── write exit status
    └── print unique sentinel
```

Do not reconstruct argv by naive string joining.

Use safe shell quoting, a generated wrapper script, or another mechanism that preserves argument boundaries exactly.

Prompts may contain:

- quotes;
- newlines;
- shell metacharacters;
- Unicode;
- Markdown;
- code blocks.

They must never become shell injection.

---

# 9. Completion Detection

Use Herdr pane primitives to determine when the wrapped command finishes.

A unique run-specific completion marker is recommended, for example conceptually:

```text
__HERMES_LAB_COMPLETE_<nonce>__:<exit-code>
```

Then wait through Herdr for that marker.

Requirements:

- timeout must still be enforced;
- timeout maps to existing `FAILED_TIMEOUT` where appropriate;
- non-zero worker exit is still returned to the adapter/controller;
- partial stdout/stderr should remain available for diagnosis;
- completion markers must not be confused with model output.

Do not rely only on:

```text
agent becomes idle
```

because Sprint 04 is preserving one-shot CLI execution semantics.

---

# 10. Herdr Observability

While a worker command runs inside a Herdr pane, the user should be able to observe the real process from the Herdr UI.

The controller should retain enough runtime metadata to report something like:

```text
Phase: agent_refactor
Agent: claude
Backend: herdr
Pane: <runtime pane id>
```

Do not make agent sidebar recognition a correctness requirement in Sprint 04.

Agent recognition is valuable observability, but the deterministic completion contract remains:

```text
process exit + captured output + adapter validation
```

If Herdr recognizes the foreground Claude/Codex/Agy process, that is a runtime/UI benefit.

If recognition temporarily reports `unknown`, the phase should not automatically fail if process execution and adapter validation are otherwise valid.

---

# 11. Why `agent start` Is Deferred

Herdr provides richer agent primitives:

```text
agent start
agent prompt
agent wait
agent read
```

These are deliberately **not the default S04 execution contract**.

Reason:

```text
Subprocess mode
Claude returns JSON
Agy returns stream-JSON
Codex returns deterministic one-shot output

Interactive Herdr mode
Agent produces terminal transcript
Herdr reports lifecycle state
```

Those are different result contracts.

A future sprint may introduce:

```text
SessionfulHerdrBackend
```

or an execution mode such as:

```json
{
  "backend": "herdr",
  "mode": "interactive"
}
```

after the one-shot Herdr backend is proven.

Do not mix that experiment into Sprint 04.

---

# 12. Backend Selection

Add backend selection at sprint or runner level.

Recommended default:

```json
{
  "execution_backend": "subprocess"
}
```

Sprint 04 experiment:

```json
{
  "execution_backend": "herdr"
}
```

Allow CLI override if useful:

```bash
python3 runner/run-hermes-sprint.py \
  --spec sprints/lab-s04.json \
  --backend herdr
```

Recommended precedence:

```text
CLI override
    ↓
sprint spec
    ↓
default subprocess
```

Unknown backend:

```text
FAILED_UNKNOWN_BACKEND
```

Do not silently reinterpret unknown values.

---

# 13. Backend Registry

Use the same principle as the agent registry.

Conceptually:

```python
BACKEND_REGISTRY = {
    "subprocess": SubprocessBackend,
    "herdr": HerdrBackend,
}
```

Avoid:

```python
if backend == "subprocess":
    ...
elif backend == "herdr":
    ...
```

inside controller execution flow.

The controller should resolve the backend once and use its interface.

---

# 14. Herdr Process Wrapper Safety

This is a critical Sprint 04 requirement.

Do not execute:

```python
" ".join(command)
```

inside `sh -c`.

Use one of:

### Preferred: generated wrapper script

Create a temporary script under the local run directory that receives pre-encoded argv safely.

Example idea:

```text
run_dir/
└── wrappers/
    └── verification_codex.sh
```

The script itself must quote arguments safely.

or:

### Alternative: shell-safe argv encoding

Use Python's shell quoting rigorously and cover it with tests.

The wrapper must never allow the model prompt to inject:

```text
;
&&
|
$()
backticks
redirects
new commands
```

as shell syntax.

The prompt is data.

---

# 15. Timeout and Cancellation

SubprocessBackend already has Python timeout semantics.

HerdrBackend must provide equivalent behavior.

When a Herdr worker times out:

1. mark the execution as timeout;
2. attempt to interrupt the foreground worker cleanly;
3. do not close unrelated panes/workspaces;
4. preserve logs;
5. return/raise `FAILED_TIMEOUT`;
6. leave enough state for human inspection where practical.

Use targeted pane/agent control only.

Never stop the entire Herdr server because one sprint phase timed out.

---

# 16. Pane Lifecycle

Default Sprint 04 behavior:

```text
successful run
    → keep worker panes alive until sprint finishes
    → optionally keep workspace for inspection

failed run
    → preserve failed worker pane for inspection
```

Add an explicit cleanup mode if needed:

```text
--herdr-cleanup never
--herdr-cleanup success
--herdr-cleanup always
```

Do not delete or close a user's pre-existing Herdr workspace.

Only clean resources created by this runner instance.

For the initial implementation, a simpler boolean such as:

```text
keep_herdr_workspace: true
```

is acceptable.

Do not over-engineer lifecycle policy.

---

# 17. Sprint 04 Spec

Create:

```text
sprints/lab-s04.json
```

Recommended skeleton:

```json
{
  "sprint_id": "lab-s04",
  "name": "Execution Backend Abstraction + Herdr Runtime",
  "canonical_repo": "/home/lystiger/hermes-lab",
  "base_ref": "6452c44ea72bb4886f08d4753bc8cf06f9e6c45b",
  "target_branch": "s04/integration",
  "worktree_root": "/home/lystiger/hermes-worktrees/hermes-lab-s04",
  "runs_root": "/home/lystiger/hermes-runs",
  "execution_backend": "herdr",
  "limits": {
    "max_changed_files": 20,
    "timeout_seconds": 600
  },
  "phases": [
    {
      "name": "backend_implementation",
      "agent": "claude",
      "worktree_dir": "claude",
      "branch": "s04/claude",
      "prompt_file": "prompts/s04-claude.md",
      "expected_handoff": "HANDOFF_CLAUDE.md",
      "commit_message": "feat(s04): add execution backend abstraction and Herdr runtime",
      "cmd_options": {
        "model": "sonnet",
        "max_turns": 40,
        "permission_mode": "dontAsk",
        "output_format": "json"
      }
    },
    {
      "name": "backend_verification",
      "agent": "codex",
      "worktree_dir": "codex",
      "branch": "s04/codex",
      "prompt_file": "prompts/s04-codex.md",
      "expected_handoff": "HANDOFF_CODEX.md",
      "commit_message": "test(s04): verify subprocess and Herdr execution backends",
      "cmd_options": {
        "sandbox": "workspace-write",
        "ephemeral": true
      }
    }
  ]
}
```

Important bootstrapping note:

The S04 controller code that adds `HerdrBackend` cannot reliably use that not-yet-existing backend to implement itself from the beginning.

Therefore development should use a staged bootstrap.

---

# 18. Bootstrap Strategy

This is important.

Do not create a circular dependency:

```text
Need S04 code to run HerdrBackend
but
Need HerdrBackend to run Claude to write S04 code
```

Use two stages.

## Stage A — Build S04 using SubprocessBackend

Claude implements:

- backend abstraction;
- SubprocessBackend;
- HerdrBackend;
- tests;
- new sprint spec.

Run and merge that implementation using the existing subprocess execution path.

## Stage B — Dogfood HerdrBackend

After the Herdr backend exists and tests pass:

run an integration/dogfood workflow with:

```text
--backend herdr
```

Codex should perform the independent verification phase through Herdr.

This gives the sprint an explicit proof:

```text
S04 implementation built with stable backend
        ↓
HerdrBackend becomes available
        ↓
Codex verification runs through Herdr
        ↓
same controller gates
        ↓
READY_FOR_REVIEW
```

Do not attempt self-hosting before the backend exists.

---

# 19. Recommended S04 Development Flow

```text
main
 │
 ▼
s04/integration
 │
 ▼
Claude
 │
 │ backend = subprocess
 │
 ├── ExecutionBackend
 ├── SubprocessBackend
 ├── HerdrBackend
 ├── backend registry
 ├── tests
 └── HANDOFF_CLAUDE.md
 │
 ▼
controller validation
 │
 ▼
merge
 │
 ▼
Codex
 │
 │ backend = herdr
 │
 ├── adversarial verification
 ├── timeout tests
 ├── quoting/injection tests
 ├── failure-path tests
 └── HANDOFF_CODEX.md
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

If using a single global backend per run makes staged bootstrapping awkward, permit an **explicit per-phase backend override**:

```json
{
  "execution_backend": "subprocess",
  "phases": [
    {
      "name": "backend_implementation",
      "execution_backend": "subprocess"
    },
    {
      "name": "backend_verification",
      "execution_backend": "herdr"
    }
  ]
}
```

Recommended precedence:

```text
phase override
    ↓
CLI override if deliberately global
    ↓
sprint backend
    ↓
subprocess
```

Keep the precedence documented and tested.

---

# 20. Required Tests

## 20.1 Backend registry

Test:

- `subprocess` resolves;
- `herdr` resolves;
- unknown backend fails;
- backend selection precedence is deterministic.

## 20.2 Subprocess parity

Prove that existing behavior remains unchanged.

Test:

- successful command;
- stdout capture;
- stderr capture;
- non-zero exit;
- timeout;
- missing executable;
- permission error;
- adapter validation still runs.

## 20.3 Herdr preflight

Mock Herdr CLI responses.

Test:

- missing `herdr`;
- server unavailable;
- malformed Herdr JSON;
- failed workspace creation;
- failed pane creation;
- failed pane command;
- timeout.

Unit tests must not require a running Herdr server.

## 20.4 Herdr JSON parsing

Test exact parsing of:

```text
workspace id
root pane id
split/new pane id
command errors
```

Do not regex IDs from human-readable output.

## 20.5 Command safety

Mandatory adversarial cases:

```text
simple prompt
prompt with newline
prompt containing single quotes
prompt containing double quotes
prompt containing ;
prompt containing &&
prompt containing |
prompt containing $(...)
prompt containing backticks
Vietnamese Unicode
large Markdown/code-block prompt
```

Prove that all remain a **single agent argument/payload**.

No injected shell command may execute.

## 20.6 Completion sentinel

Test:

- correct sentinel recognized;
- wrong nonce ignored;
- model output containing a similar string does not complete the run;
- non-zero exit propagated;
- timeout propagated;
- partial output preserved.

## 20.7 Resource ownership

Test that cleanup only targets:

```text
workspace/panes created by this run
```

and never:

```text
pre-existing user workspaces
unrelated panes
the entire Herdr server
```

## 20.8 Controller invariants

Re-run existing tests proving:

- agent adapter contains no Git integration;
- backend contains no controller Git promotion logic;
- changed-file limit remains mandatory;
- handoff remains mandatory;
- test gate remains mandatory;
- `READY_FOR_REVIEW` requires pytest;
- deterministic worktree resets remain unchanged.

---

# 21. Integration / Smoke Tests

Add integration tests that are skipped unless Herdr is available.

But executable presence alone is not enough for the full test.

A Herdr smoke test should detect whether the local server is reachable and skip cleanly when it is not.

Smoke test should NOT call an AI provider.

Use a harmless shell process first:

```text
create workspace
    ↓
create pane
    ↓
run echo/test command
    ↓
wait for sentinel
    ↓
read result
```

Then add one optional manually-invoked real-agent smoke test.

Do not make CI depend on paid agent/API access.

---

# 22. Real Dogfood Acceptance Test

After unit tests pass, manually run one real worker through Herdr.

Recommended first target: **Codex verification**.

Acceptance:

```text
Herdr UI visibly shows the worker pane
        +
worker operates only in assigned worktree
        +
controller receives deterministic result
        +
adapter validation passes
        +
handoff exists
        +
controller commits/merges
        +
pytest passes
```

---

# 23. Runtime Metadata

Extend phase result locally with safe runtime fields if useful:

```json
{
  "phase": "backend_verification",
  "agent": "codex",
  "backend": "herdr",
  "status": "SUCCESS",
  "changed_files_count": 4
}
```

Local full summary may additionally contain:

```json
{
  "herdr_workspace_id": "...",
  "herdr_pane_id": "..."
}
```

Sanitized report should include only stable information needed for evidence, preferably:

```json
{
  "backend": "herdr"
}
```

Avoid machine/session-specific IDs in committed evidence.

---

# 24. Logging

Keep existing logs.

Recommended additions:

```text
<run_dir>/
├── runner.log
├── run_summary.json
│
├── backend_implementation_claude_stdout.log
├── backend_implementation_claude_stderr.log
│
├── backend_verification_codex_stdout.log
├── backend_verification_codex_stderr.log
│
└── herdr/
    ├── commands.log
    └── runtime.json
```

`herdr/commands.log` must not contain raw prompts if doing so creates a secret/privacy risk.

Prefer recording:

```text
operation
target pane
exit status
timestamp
```

rather than complete command payloads.

---

# 25. Security Boundaries

Herdr does not replace worker sandboxing.

Keep all existing worker restrictions:

```text
Antigravity
    → scoped worktree permissions
    → .git writes denied

Claude
    → disallowedTools Git mutation rules
    → read-only Git inspection allowed

Codex
    → workspace-write sandbox forced
```

Herdr adds:

```text
runtime isolation by pane
persistent observability
detachable execution
runtime targeting
```

It does not become Git policy authority.

---

# 26. Failure Semantics

Suggested mappings:

```text
Herdr CLI missing
    → FAILED_HERDR_EXECUTABLE_MISSING

Herdr server/socket unavailable
    → FAILED_HERDR_UNAVAILABLE

Herdr returns malformed JSON
    → FAILED_HERDR_PROTOCOL

Herdr command returns non-zero
    → FAILED_HERDR_COMMAND

Worker timeout inside Herdr
    → FAILED_TIMEOUT

Worker exits non-zero
    → FAILED_AGENT_EXECUTION

Agent result malformed
    → existing adapter-specific failure
```

Do not convert every Herdr error into `FAILED_AGENT_EXECUTION`.

Runtime failures and agent failures should remain distinguishable.

---

# 27. Non-Goals

Sprint 04 must NOT implement:

- interactive/sessionful Herdr workers as the default;
- `agent start` / `agent prompt` orchestration for production runs;
- automatic session resume;
- multi-agent parallel execution;
- dynamic agent planning;
- LLM-controlled Git;
- remote Herdr execution;
- SSH orchestration;
- phone control;
- automatic approval handling;
- agent-to-agent chat;
- a message bus;
- production deployment;
- removal of SubprocessBackend.

These are future experiments.

---

# 28. Coding Ownership

## Claude Code — Primary Implementer

Claude should implement:

- `ExecutionBackend`;
- `ExecutionRequest`;
- `ExecutionResult`;
- backend registry;
- `SubprocessBackend`;
- `HerdrBackend`;
- runner/backend wiring;
- staged backend selection;
- safe command wrapper;
- unit tests;
- documentation;
- `HANDOFF_CLAUDE.md`.

Claude should use **SubprocessBackend during implementation**.

## Codex — Independent Reviewer / Herdr Dogfood Worker

Codex should verify:

- backend abstraction quality;
- subprocess parity;
- Herdr JSON parsing;
- timeout behavior;
- command injection resistance;
- resource cleanup ownership;
- output/log correctness;
- no Git-boundary regression;
- no silent fallback;
- sanitized evidence behavior.

Codex should be the first real worker executed through Herdr after the implementation exists.

Produce:

```text
HANDOFF_CODEX.md
```

with:

- tests run;
- Herdr smoke-test result;
- defects found/fixed;
- remaining runtime risks.

## Hermes — Supervisor Only

Hermes may be used interactively to:

- inspect the run;
- explain failures;
- inspect worker panes;
- inspect logs;
- help the human navigate Herdr.

Hermes does not become the deterministic sprint controller.

---

# 29. Definition of Done

Sprint 04 is complete only when:

- [ ] `ExecutionBackend` abstraction exists.
- [ ] Backend registry exists.
- [ ] `SubprocessBackend` preserves Sprint 03 behavior.
- [ ] `HerdrBackend` exists.
- [ ] Herdr backend selection is explicit.
- [ ] Unknown backend fails safely.
- [ ] No silent Herdr → subprocess fallback exists.
- [ ] Herdr preflight exists.
- [ ] Herdr JSON IDs are parsed rather than predicted.
- [ ] Worker argv/prompt handling is shell-injection safe.
- [ ] Herdr worker stdout is captured.
- [ ] Herdr worker stderr is captured.
- [ ] Herdr worker exit code is captured.
- [ ] Herdr timeout maps correctly.
- [ ] Failed Herdr resources remain inspectable where practical.
- [ ] Cleanup only touches runner-owned Herdr resources.
- [ ] Antigravity permission behavior remains unchanged.
- [ ] Claude Git mutation restrictions remain unchanged.
- [ ] Codex remains forced to `workspace-write`.
- [ ] Deterministic worktree reset remains unchanged.
- [ ] Controller remains sole Git promotion authority.
- [ ] Full unit suite passes.
- [ ] Herdr shell smoke test passes locally.
- [ ] At least one real Codex verification phase runs through Herdr.
- [ ] Integration pytest passes.
- [ ] Final status reaches `READY_FOR_REVIEW`.
- [ ] Sanitized evidence records the selected backend.
- [ ] Subprocess backend remains available as fallback/reference.

---

# 30. Sprint 04 Principle

> **Change the transport, not the governance.**

Sprint 04 should prove that:

```text
same agent
same worktree
same prompt
same controller
same validation
same Git policy
same tests

but

different runtime
```

If the Herdr backend works, the harness gains persistent, inspectable execution without surrendering deterministic control.

---

# 31. Future Direction After Sprint 04

Only after Sprint 04 is stable should the lab consider a sessionful backend based on Herdr agent primitives.

Future architecture:

```text
ExecutionBackend
├── SubprocessBackend
├── HerdrOneShotBackend
└── HerdrSessionBackend
       │
       ├── agent start
       ├── agent prompt
       ├── agent wait
       ├── agent read
       └── native session resume
```

That future sprint changes **agent interaction semantics**.

Sprint 04 changes only **execution hosting**.

Keep those experiments separate.
