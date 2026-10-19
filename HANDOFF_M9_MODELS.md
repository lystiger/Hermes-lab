# M9 models handoff

Implemented descriptors, per-model effort validation, dynamic Codex discovery, grouped agy IDs,
and reported model recording. Existing GET fields remain. API agent IDs remain unchanged:
Antigravity is exposed as `gemini`; registry and PUT also accept `antigravity` and `agy`.

## GET /agents/models

Representative fixture-backed response with real model shapes (availability and reported IDs depend
on local CLI state; this is not a claim that live CLIs were queried):

```json
{
  "claude": {
    "configured": {"default": null, "effort": null},
    "allowed": ["sonnet", "opus", "haiku", "claude-sonnet-4-6"],
    "models": [
      {"id": "sonnet", "label": "Sonnet (latest)", "efforts": []},
      {"id": "opus", "label": "Opus (latest)", "efforts": []},
      {"id": "haiku", "label": "Haiku (latest)", "efforts": []},
      {"id": "claude-sonnet-4-6", "label": "claude-sonnet-4-6", "efforts": []}
    ],
    "lastUsed": {
      "model": "claude-sonnet-4-6", "effort": null, "source": "reported",
      "requestedModel": null, "requestedEffort": null, "requestedSource": "cli-default"
    }
  },
  "codex": {
    "configured": {"default": "gpt-6.1-sol", "effort": "high"},
    "allowed": ["gpt-6.1-sol"],
    "models": [
      {"id": "gpt-6.1-sol", "label": "GPT-6.1-Sol", "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"]}
    ],
    "lastUsed": {
      "model": "gpt-6.1-sol", "effort": "high", "source": "reported",
      "requestedModel": "gpt-6.1-sol", "requestedEffort": "high", "requestedSource": "config"
    }
  },
  "gemini": {
    "configured": {"default": "gemini-3.8-flash", "effort": "high"},
    "allowed": ["gemini-3.8-flash", "claude-sonnet-4-6", "claude-opus-4-6-thinking", "gpt-oss-120b"],
    "models": [
      {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "efforts": ["low", "medium", "high"]},
      {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (Thinking)", "efforts": []},
      {"id": "claude-opus-4-6-thinking", "label": "Claude Opus 4.6 (Thinking)", "efforts": []},
      {"id": "gpt-oss-120b", "label": "GPT-OSS 120B", "efforts": ["medium"]}
    ],
    "lastUsed": {
      "model": "gemini-3.8-flash", "effort": "high", "source": "reported",
      "requestedModel": "gemini-3.8-flash", "requestedEffort": "high", "requestedSource": "config"
    }
  }
}
```

Before any run, `lastUsed` is null. Without a report it retains the resolved launch setting;
without a requested/configured model this is `{model: null, effort: null, source: "cli-default"}`.
Runtime metadata and completion/failure events include `reportedModel` (null when absent).
Codex cache is re-read each request, so mtime changes and atomic replacements are immediately visible.
The cache path can be overridden with `HERMES_CODEX_MODELS_CACHE`.

## PUT examples

```http
PUT /agents/codex/model
Content-Type: application/json

{"model":"gpt-6.1-sol","effort":"ultra"}
```

Accepted only if that model offers ultra. Returns `{ "default": "gpt-6.1-sol", "effort": "ultra" }`.

```http
PUT /agents/gemini/model
Content-Type: application/json

{"model":"gemini-3.8-flash","effort":"high"}
```

Returns `{ "default": "gemini-3.8-flash", "effort": "high" }`. Legacy body
`{"model":"gemini-3.8-flash-high"}` stores the same normalized setting.
With null effort, launch chooses medium if offered, otherwise the first offered effort.
`{"model":"gpt-oss-120b","effort":"high"}` returns 400 with the supplied sample list.

```http
PUT /agents/claude/model
Content-Type: application/json

{"model":"sonnet"}
```

Returns `{ "default": "sonnet", "effort": null }`. A reported full Claude ID is also accepted
once recorded in the seen file. Claude effort choices remain empty.

## Files changed

- `agent_models.py`: descriptors, cache parsing, grouping, mapping, per-model validation, seen persistence.
- `runner/agents/base.py`: post-run reporting, requested setting retention, runtime/event metadata.
- `runner/agents/{claude,codex,antigravity}.py`: output extraction and agy CLI ID mapping.
- `.gitignore`: ignore `config/agent_models.seen.json`.
- `.agent/DECISIONS.md`: D-020a.
- `tests/conftest.py`: isolate Codex cache from user state.
- `tests/test_agent_models.py`: cache, API, grouping, mapping and reporting fixtures.
- `tests/test_runner.py`: new agy argv expectation; installed Claude help check explicitly opt-in
  with `HERMES_TEST_LIVE_AGENTS=1` to avoid a real CLI in fixture runs.
- `HANDOFF_M9_MODELS.md`: this handoff.

## Validation and remaining work

Exact focused command:

```sh
/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_agent_models.py tests/test_runner.py -q -p no:cacheprovider
```

Final result: **94 passed, 2 skipped, 43 subtests passed in 0.97s**.
`git diff --check` passed. Full suite was not run, per operator instructions; Hermes runs it afterwards.
Live CLI verification remains external. Initial installed-Claude check failed because its mise shim
attempted installation: `mise ERROR Failed to install aqua:anthropics/claude-code@latest: Read-only file system (os error 30)`;
it also reported DNS resolution failure. That check now requires explicit live-test opt-in.
No Git metadata was changed and no commit was created.
