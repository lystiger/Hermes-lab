# D-015: Agent model — runtime, model, role, persona, instance

Status: proposal (lead), for Codex review before implementation.

## Problem
Hermes describes "agents" as three fixed entities with a hardcoded model and a fixed pipeline phase
(`personas/agent_service.py` KNOWN_AGENT_METADATA: gemini→antigravity-2.5-pro→BUILD, claude→claude-sonnet-4-5→HARDEN,
codex→gpt-5-codex→VERIFY), and personas that bake a role into the character (`personas/persona.py` DEFAULT_PERSONAS:
"Calm Hardener", "Precision Verifier"). Reality since Steps 3–6: the model is chosen per task (`options.model`), roles are
per task (`metadata.role`; D-011 keeps them through fallbacks), and work runs as concurrent instances on OpenRig seats,
Herdr panes or subprocesses (D-009). `GET /agents` therefore reports facts that are not true, and LysControl mirrors them.

## Five concepts (each with one source of truth)
| Concept | Meaning | Source of truth | Never |
|---|---|---|---|
| **Runtime** | the CLI Hermes launches: `claude`, `codex`, `agy` | `runner/agents/registry.py` adapters | hardcoded model or phase |
| **Model** | the LLM used by ONE execution | requested: task `options.model` (or runtime default, shown as "runtime default"); reported: adapter `runtime_metadata.model` when the CLI states it | a per-agent constant |
| **Role** | what a task asks for: builder, hardener, verifier, repairer, planner… | task `metadata.role` | a property of an agent or persona |
| **Persona** | a named character with voice and art (Claude, Codex, Gemini, Hermes) bound to a runtime | persona file, transcribed from the character sheet | invented lore; role-specific traits |
| **Instance** | one execution: persona + runtime + model + role + backend resource + job/task | D-009 execution events + runs | — |

Binding: each runtime speaks through one persona by default (`claude`→Claude, `codex`→Codex, `agy`→Gemini;
the runtime itself is Hermes). A persona may later be bound to several runtimes; the instance records which.

## Personas: files, provenance, precedence
- One file per persona: `personas/catalog/<id>.json` (`claude`, `codex`, `gemini`, `hermes`), loaded by the existing
  `PersonaLoader` (sanitised). `DEFAULT_PERSONAS` becomes the loader's fallback only for unknown runtimes.
- **Provenance rule (no hallucination):** every descriptive field is either transcribed verbatim from the character sheet
  (`design-reference/cards/<id>.png` in LysControl) or left empty. Each field records its source:
  `"source": {"traits": "sheet: left column", "quote": "sheet: header quote", ...}`. Nothing is paraphrased into new lore.
  Hermes has no sheet (emblem only): its persona has a name, a one-line factual summary ("Hermes runtime: plans, schedules
  and verifies work") and no invented personality until the user writes one.
- **Role-agnostic:** persona traits/voice come from the sheet; role behaviour comes from the task role section of the
  prompt. The old role-baked texts ("Calm Hardener") are removed.
- **Precedence (unchanged, now explicit in the file schema):** controller/safety rules > operator instructions > task
  and role rules (e.g. verifier no-mutation) > persona voice. A persona can change tone, never truthfulness, permissions,
  or output protocol (result file, handoff).
- **Visual:** `accentColor` = measured from the art (user-approved: claude #CCA27D, codex #7A8ECE, gemini #9686E1,
  hermes #CBA35C); `portrait`, `fullArt`, `sheet` URLs point at LysControl public assets (cutouts once approved).

## API
- `GET /agents` → one entry per **persona/runtime**, no fixed model or phase:
  `{id, displayName, runtime, persona{name, title, summary, quote, traits[], source{}}, visual{accentColor, portraitUrl,
  fullArtUrl, sheetUrl}, available (runtime CLI on PATH), supportedBackends[], status (BUSY if any live instance, else
  IDLE — derived, not set by hand), activeInstances, recentModels[] (distinct reported/requested models from recent runs,
  each with "reported"|"requested"|"runtime default")}`.
  Transitional: `model`, `phase`, `role`, `capabilities` stay in the payload as `null` for one release so old clients
  render "unknown" instead of crashing; LysControl M6 stops reading them.
- `GET /agents/{id}` → the same plus `recentInstances[]` (last N runs: job, task, role, model + provenance, backend,
  outcome, started/finished) from the run store.
- D-009 execution metadata gains `persona`, `runtime`, `model` (+ `modelSource`), `role` (allowed-keys list updated).
- `GET /execution` resources gain the same fields, so a seat shows who is in it.

## OpenRig gap
OpenRig seats launch the `claude-code` runtime with its configured default model; Hermes does not yet pass a model into
the seat spec. Until it does, OpenRig instances report `model: null, modelSource: "runtime default"` — never a guess.
Passing the requested model into the seat is a separate, testable change (H5).

## Implementation steps (Hermes)
- **H1** persona catalog files transcribed from the sheets with per-field provenance; loader + fallback; prompt rendering
  role-agnostic with the precedence block; tests that no persona field lacks a source.
- **H2** `GET /agents` and `GET /agents/{id}` per this schema; remove KNOWN_AGENT_METADATA models/phases/sigils; status
  and recentModels derived from live instances and runs; transitional nulls.
- **H3** requested/reported model, role, persona, runtime on runs and D-009 events; registry and snapshot carry them.
- **H4** availability per runtime (CLI on PATH) and supportedBackends (via `supports_agent`).
- **H5** (optional) pass requested model into OpenRig seats.
Each step: tests, suite green, Codex review, merge. Then LysControl **M6**: Agents = persona roster with art and
recent instances; Execution = instances; Queue loses fixed BUILD/HARDEN/VERIFY columns for role/model/backend filters.

## Open questions for the user
1. Persona text for Hermes (no sheet): leave minimal, or will you write one?
2. Should one persona ever speak for several runtimes (e.g. Claude persona for both `claude` CLI and an OpenRig
   claude-code seat — yes by default; for other providers — no)?
