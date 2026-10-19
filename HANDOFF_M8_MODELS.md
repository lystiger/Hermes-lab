# M8 model registry handoff — D-020

Implemented the model registry and next-phase configuration boundary. Full-suite verification is
limited by this sandbox; see validation below.

## LysControl API contract

Agent keys match `GET /agents`: `gemini`, `claude`, `codex` for the built-in registry.
PUT also accepts runner aliases `antigravity` and `agy` for Gemini. Only registered agents are exposed.

`GET /agents/models` → HTTP 200, object keyed by agent ID. Example (allowed Codex and Gemini
lists depend on the host; this shows the Claude entry):

```json
{
  "claude": {
    "configured": {"default": "opus", "effort": null},
    "allowed": ["sonnet", "opus", "haiku"],
    "lastUsed": {"model": "sonnet", "effort": null, "source": "phase"}
  }
}
```

`lastUsed` is null until a recorded start exists. Its model can also be null when the CLI
chooses its own default; Hermes does not fabricate a resolved provider model ID. Aliases such
as `sonnet` are the actual CLI selection passed at launch, not a claim about a provider's
underlying version. Changing configuration does not change lastUsed.

`PUT /agents/claude/model` request:

```json
{"model": "opus", "effort": null}
```

HTTP 200 response:

```json
{"default": "opus", "effort": null}
```

`PUT /agents/codex/model` request (choose a model from GET, never invent an ID):

```json
{"model": "gpt-5-codex", "effort": "high"}
```

HTTP 200 response:

```json
{"default": "gpt-5-codex", "effort": "high"}
```

Unknown agent → 404 `{"detail":"Unknown agent"}`. Disallowed model → 400
`{"detail":"Model is not in the agent allowlist"}`. Unsupported effort → 400
`{"detail":"Unsupported reasoning effort for agent"}`. Invalid JSON/schema → 422.
Omitting effort resets it to null. Claude accepts null only; Codex accepts null, minimal, low,
medium, high, xhigh; agy accepts null, low, medium, high. Browser clients submit only choices
returned by GET. The configured origins already permit PUT via the existing CORS wildcard.

`GET /agents` keeps its existing list schema; `model` now equals configured.default or null.

## Resolution, files and persistence

- Phase model overrides configured model; without either, no model flag is sent and the CLI chooses.
  An explicit phase effort overrides configured effort independently. The event source identifies
  the model's source. A setting resolves once before command construction; changes during launch
  apply to a subsequent phase.
- `agent.started` metadata includes `model`, `effort`, `source` alongside existing command and phase.
  API ingress records this metadata too, covering separate runner processes.
- `agent_models.py`: shared registry, CLI discovery, resolution, locked atomic writes and lastUsed.
- `config/agent_models.example.json`: shipped per-agent default/effort/allowed template. Defaults
  are null so the example invents no configured selection.
- `config/agent_models.json`: ignored local choices, created locally. Without a local Codex default
  key, Hermes imports model and model_reasoning_effort from `~/.codex/config.toml`; that model
  also joins the Codex allowlist. Claude's allowlist is fixed. agy IDs come from `agy models`,
  text before the first tab, cached 60 seconds, with example/local fallback on CLI failure.
- Local writes use a same-directory temporary file, fsync, os.replace and directory fsync.
  A process/thread lock serializes read-modify-write; failed replacement preserves the old file.
- `config/agent_models.last_used.json`: separate ignored durable run selections.
  `config/agent_models.lock`: shared lock. API and runner must use the same config path;
  `HERMES_AGENT_MODELS=/absolute/path/agent_models.json` overrides it for separate deployments.
- `runner/agents/base.py`: launch snapshot and event metadata; `antigravity.py`, `claude.py`,
  `codex.py`: configured fallback and CLI flags, including Codex reasoning effort.
- `personas/agent_service.py`: registry-backed model labels; `agent_state_reducer.py`: ingress recording.
- `main.py`: model API routes and request schema. `.gitignore`: excludes local settings/state.
- `.agent/DECISIONS.md`: D-020. `tests/test_agent_models.py`: registry/API/adapter coverage.
  `tests/conftest.py`: isolate all tests from real model settings and local Codex config.

## Validation

Nine model-registry tests pass: API allowlist/effort rejection and unknown IDs, persistence round trip,
GET /agents source, CORS PUT, Codex TOML import, precedence, fake agy discovery/cache/fallback,
atomic failure preservation/cleanup, CLI flags, event metadata, ingress lastUsed, concurrent writes,
and settings frozen during launch. Test count is nine; several cases contain multiple assertions.

Required command:

```sh
/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke
```

The unmodified command stalls at
`tests/test_backend_contract.py::test_runtime_dispatches_new_backend_and_releases_it_once_on_success`.
A diagnostic run with `-vv -o faulthandler_timeout=25` shows the asyncio event loop in selector.select
while its worker thread is idle. The restricted sandbox also prevents the installed Claude shim
from working. The adapter regression run reports 88 passed, 1 skipped, 43 subtests passed, 1 failed:

```text
FAILED tests/test_runner.py::TestAgentRegistryAndCommands::test_installed_claude_supports_disallowed_tools_flag
AssertionError: 1 != 0 : mise ERROR Failed to install aqua:anthropics/claude-code@latest: Read-only file system (os error 30)
```

The same output reports DNS resolution failure. Reproduce directly with `claude --help`.
A separate broad diagnostic run uses a temporary plugin under `/tmp/hermes-model-check` to bound
selector polling at 50 ms, avoiding the blocked thread wakeup; this does not alter repository code.
Diagnostic result: **596 passed, 6 skipped, 31 failed, 3 errors, 43 subtests passed** in 80.86 s.
Failures/errors show writes outside writable roots (`~/hermes-runs`, sibling worktrees), denied
socket binds (`PermissionError: [Errno 1] Operation not permitted`), and the Claude shim failure.
Two acceptance failures report BLOCKED instead of COMPLETED after denied sibling-worktree creation.
Full output: `/tmp/hermes-models-polled.log`; stalled-run trace: `/tmp/hermes-models-suite.log`.
Reproduce the diagnostic (temporary plugin is outside the repository):

```sh
PYTHONPATH=/tmp/hermes-model-check PYTEST_ADDOPTS='-p sandbox_poll' \
  /home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke
```

Unmodified focused registry + main/control API checks: **25 passed**:

```sh
/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_agent_models.py tests/test_main.py tests/test_control_api.py -q
```

## Remaining

Run the exact required suite on a host with normal thread wakeups, loopback sockets and an installed
Claude binary. A clean full-suite result has not been established in this sandbox. LysControl client
implementation is outside this phase. No Git staging, commits or metadata changes were performed.
