# Role: BUILDER — Hermes M8, phase 3: model registry (D-020)

You are the BUILDER and may edit source files. Hermes owns Git: do not run
git add, commit, merge, push, reset, checkout, or alter Git metadata. Work only
in your assigned worktree (the Hermes-lab repository). Run tests with
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke`.
Phases 1 and 2 are already in your worktree; do not redo them.

Read `personas/agent_service.py` (it has static, now wrong "model" labels such
as "antigravity-2.5-pro"), `runner/agents/antigravity.py` (agy accepts `model`
and `effort` options), `runner/agents/codex.py`, `runner/agents/claude.py`,
`main.py` (`GET /agents`) and `.agent/DECISIONS.md`.

## Goal

LysControl will show and change which model each agent uses. Hermes owns the
truth: an allowlist per agent, a configured default, and a record of the model
each run actually used. The browser must never send a raw model string to a CLI.

## Step 1: decision D-020

Append `## D-020: Model registry (2026-10-19)` to `.agent/DECISIONS.md`
(follow the existing format): allowlist per agent; `GET /agents/models`;
`PUT /agents/{id}/model`; the change applies to the next phase only; the
configured value and the model actually used are different fields; Codex
reasoning effort and agy effort are part of the same setting.

## Step 2: implement

- Config file `config/agent_models.json` (create `config/` if needed; keep it
  out of source control if it holds local choices: add it to `.gitignore` and
  ship `config/agent_models.example.json`). Shape per agent:
  `{"default": "...", "effort": "...", "allowed": ["...", "..."]}`.
- Allowlists: claude: `sonnet`, `opus`, `haiku`; codex: read the models from
  `~/.codex/config.toml` default plus a small static list in the example file;
  antigravity: parse `agy models` output (id before the first tab) with a short
  cache (60 s) and a safe fallback to the example list when the CLI is missing.
- `GET /agents/models` returns, per registered agent: `configured` (default and
  effort), `allowed`, and `lastUsed` (the model recorded by the most recent run
  of that agent, or null).
- `PUT /agents/{id}/model` with `{"model": "...", "effort": "..."}`: 400 if the
  model is not in the allowlist, 404 for an unknown agent; persists to the
  config file atomically; returns the new setting.
- Adapters read the configured default when the phase options give no `model`
  (a phase option still wins). antigravity: `--model`/`--effort`; claude:
  `--model` (already); codex: `--model`.
- Record the model actually used on the run: add it to the `agent.started`
  event metadata (`model`, `effort`, source `phase` or `config` or `cli-default`).
- Fix the stale static labels in `personas/agent_service.py`: `GET /agents`
  `model` must come from the registry (configured default) and be `null`
  instead of a made-up value when nothing is configured.
- CORS: `PUT` must be allowed for the configured origins (see `main.py`).
- Tests: allowlist rejection, persistence round trip, precedence (phase option
  beats config beats CLI default), agy models parsing with a fake CLI,
  `GET /agents` model source, event metadata, atomic write.

## Done means

Full test suite passes. Write `HANDOFF_M8_MODELS.md`: endpoints with example
request and response JSON (LysControl will be built against it), files
changed, tests, and what is left. Stop after the handoff.
