# Role: BUILDER — Hermes M9: real model lists and efforts per model

You are the BUILDER and may edit source files. Hermes owns Git: do not run
git add, commit, merge, push, reset, checkout, or alter Git metadata. Work only
in your assigned worktree (the Hermes-lab repository).

Your sandbox blocks cross-thread asyncio wakeups, so the FULL test suite hangs
there; do not run it. Run only the focused files:
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_agent_models.py tests/test_runner.py -q -p no:cacheprovider`
(plus any new test file you add). Hermes runs the full suite afterwards.

Read `agent_models.py`, `tests/test_agent_models.py`, `runner/agents/base.py`
(around line 76, where the model is recorded), `runner/agents/claude.py`,
`runner/agents/codex.py`, `runner/agents/antigravity.py`, `main.py`
(`GET /agents/models`, `PUT /agents/{id}/model`), `personas/agent_service.py`
and `.agent/DECISIONS.md` D-020.

## Problem

The model lists are partly hardcoded and wrong, and effort is per agent
instead of per model:

- Codex: `config/agent_models.example.json` lists `gpt-5-codex`, `gpt-5.4`,
  `gpt-5.3-codex`, and efforts are hardcoded (minimal, low, medium, high,
  xhigh). The real list is in `~/.codex/models_cache.json` (kept fresh by the
  Codex CLI): `{"models": [{"slug": "gpt-6.1-sol", "display_name":
  "GPT-6.1-Sol", "visibility": "list" | "hide", "supported_reasoning_levels":
  [{"effort": "low", ...}, ...]}]}`. Each model has its own effort levels
  (low, medium, high, xhigh, max, and ultra on some).
- Antigravity (agy): `agy models` prints one line per model, `id<TAB>label`,
  and encodes effort in the id: `gemini-3.8-flash-high`, `-medium`, `-low`
  ("Gemini 3.8 Flash (High)"), plus ids with no effort suffix
  (`claude-sonnet-4-6`, `claude-opus-4-6-thinking`) and
  `gpt-oss-120b-medium`. The operator wants the model and the effort shown
  separately: model "Gemini 3.8 Flash", effort high/medium/low.
- Claude: the CLI has no list command; `--model` takes the aliases `sonnet`,
  `opus`, `haiku` or a full model name.
- "Last used" stays empty for Claude and Codex when no model option is given,
  although the CLIs print the model they used.

## Changes

### 1. Model descriptors (backwards compatible)
Add `ModelRegistry.models(agent)` returning a list of
`{"id": "<base id>", "label": "<display name>", "efforts": ["low", ...]}`.
Keep `allowed(agent)` returning the flat list of base ids, and keep every
existing field of `GET /agents/models`. Add one new field per agent:
`"models": [descriptor, ...]`. `efforts` is `[]` for a model with no effort
choice.

### 2. Codex
Read `~/.codex/models_cache.json` (path overridable with the env var
`HERMES_CODEX_MODELS_CACHE` so tests can point at a fixture). Use entries with
`visibility == "list"`; id = slug, label = display_name, efforts = the effort
names in `supported_reasoning_levels`, in file order. Always include the model
from `~/.codex/config.toml` if it is missing (label = slug, efforts from its
cache entry if present, else `[]`). If the cache is missing or invalid, fall
back to the static example list with efforts `["low","medium","high"]`.
Re-read when the file's mtime changes (no stale in-memory copy). Validate
`PUT` effort against the chosen model's own efforts.

### 3. Antigravity (agy)
Parse `agy models` into descriptors: an id matching `^(.*)-(low|medium|high)$`
is effort variant `\2` of base `\1`; group variants of one base into one
descriptor with efforts ordered low, medium, high; label = the second column
with a trailing ` (High)`/` (Medium)`/` (Low)` removed. Ids with no such suffix
become descriptors with `efforts: []`. Keep the 20 s timeout, closed stdin and
last-good-list behaviour from the earlier fix.
Launch mapping: add `agy_cli_model(model, effort)`. If `model` is a base with
efforts, the CLI id is `<base>-<effort>`; when the effort is null use
`medium` if offered, else the first effort. If `model` is already a full CLI id
(for example existing sprints pass `gemini-3.8-flash-high`), pass it through
unchanged. The adapter passes `--model <cli id>` and no longer passes
`--effort` for models whose effort is encoded in the id. `PUT` accepts the base
id and an effort from that model's efforts, and still accepts a full CLI id
(split it into base and effort when stored).

### 4. Claude
Allowed stays `sonnet`, `opus`, `haiku` (labels "Sonnet (latest)", "Opus
(latest)", "Haiku (latest)", `efforts: []`). Also append every full model id a
run has reported (see 5), kept in `config/agent_models.seen.json` (add to
`.gitignore`), label = the id.

### 5. Record the model a run actually used
After each run, read the model from the CLI's own output and record it as
`lastUsed` with `source: "reported"` (also keep what was requested):
- Claude: the JSON result's `modelUsage` object; use the key with the most
  total tokens (input + output). Add that id to the seen list.
- Codex: the header line `model: <slug>` in stdout (and `reasoning effort:
  <level>` if present).
- agy: the cli id actually passed; split into base and effort for display.
Add `reportedModel` to the run's observation/event metadata. If the CLI output
has no model, keep the existing behaviour (null, `cli-default`). Never invent a
value.

### 6. Docs and tests
Append `### D-020a` to D-020 in `.agent/DECISIONS.md`: descriptors, per-model
effort, agy id split, reported source. Tests (fixtures, no real CLIs): Codex
cache parsing incl. hidden models, per-model efforts and mtime reload, fallback
on missing/invalid file; agy grouping and label cleanup with the real sample
below, launch id mapping incl. pass-through and default effort; PUT effort
validation per model (400 for an effort the model lacks); Claude `modelUsage`
extraction and seen list; Codex header extraction; `GET /agents/models` keeps
old fields and adds `models`.

agy sample (tab separated):
```
gemini-3.8-flash-high	Gemini 3.8 Flash (High)
gemini-3.8-flash-medium	Gemini 3.8 Flash (Medium)
gemini-3.8-flash-low	Gemini 3.8 Flash (Low)
claude-sonnet-4-6	Claude Sonnet 4.6 (Thinking)
claude-opus-4-6-thinking	Claude Opus 4.6 (Thinking)
gpt-oss-120b-medium	GPT-OSS 120B (Medium)
```
Expected descriptors: `gemini-3.8-flash` "Gemini 3.8 Flash" efforts
[low, medium, high]; `claude-sonnet-4-6` "Claude Sonnet 4.6 (Thinking)" [];
`claude-opus-4-6-thinking` [] ; `gpt-oss-120b` "GPT-OSS 120B" [medium].

## Done means

Focused tests pass. Write `HANDOFF_M9_MODELS.md` with the new `GET
/agents/models` JSON (all three agents, real shapes) and `PUT` examples, files
changed, tests, and what is left. Stop after the handoff.
