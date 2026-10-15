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

## Revision 2 (2026-10-15): roles, routing, persona rules, Hermes card

### Role catalog (task field; guards attach here)
| Role | Display title | Purpose | Guard |
|---|---|---|---|
| `research` | Analyst | gather facts, compare options | read-only except its findings file; every claim cites a source |
| `scaffold` | Scaffolder | stubs, wiring, boilerplate from a clear spec | builder rights, scoped to named files |
| `build` | Engineer | implementation | builder |
| `harden` | Hardener | review, refactor, security, edge cases | builder |
| `verify` | Verifier | tests, static analysis, regressions | no mutations (existing verifier rule) |
| `repair` | Fixer | fix a failed task | inherits the failed task's runtime, model and guard (D-011) |
Unknown roles are rejected (no silent builder fallback). Optional task **focus tags** (`security`, `performance`,
`docs`) refine a role without new roles; e.g. DevSec work = `harden` + `security`. Display titles are cosmetic only.
The existing `builder`/`hardener`/`verifier` values are accepted as aliases of `build`/`harden`/`verify` for one release.

### Default routing table (configurable; per-sprint and per-phase overrides allowed)
| Role | Runtime | Model | Backend |
|---|---|---|---|
| research | agy | Gemini (runtime default) | herdr |
| scaffold | claude | claude-haiku-5-5 | herdr |
| build | claude | claude-sonnet-5-5 | herdr |
| harden | claude | claude-opus-5-5 | herdr |
| verify | codex | runtime default | herdr |
| repair | (from failed task) | (from failed task) | (from failed task) |
Herdr is the default backend for every role (D-016 A/B: equal reliability, ~2.4x faster than OpenRig). OpenRig remains
an opt-in backend; H5 (models into OpenRig seats) is dropped.

### Persona rules (decided with the user)
- Personas belong to **provider runtimes** (and Hermes itself). Several concurrent instances of one runtime share its
  persona. Subagents spawned inside a CLI are invisible to Hermes and get no persona; sub-workers Hermes spawns inherit
  the parent's persona. The Claude persona speaks for both the `claude` CLI and OpenRig claude-code seats.
- **Voice, not content:** a persona shapes the tone of handoffs, messages and summaries only. Code, diffs, test results,
  result files, verification status and errors are recorded exactly as produced; nothing is rewritten "in character".
- **Hermes** now has a character sheet (LysControl `design-reference/cards/hermes.png`, "Hermes: The Threadkeeper",
  pronouns she/her). Transcribe it like the others. The sheet's per-agent labels (Claude "Analyze", Gemini "Synthesize",
  Codex "Execute") are artistic flavour, not roles or routing. AI-garbled text on a sheet (e.g. "Attalysis") is recorded
  with the intended word plus a `"sheetText"` note, never silently copied or silently changed.
- Hermes' accent is measured from her amber Relay glow, not her crimson coat, so it stays distinct from the failure red
  (#F2555A) and Claude's caramel.


## Revision 3 (2026-10-15): Codex review r2 (AGREE WITH CHANGES), all 13 changes accepted
Full review: `docs/design/agent-model-review-r2.md`. Supersedes earlier text where they conflict (including the
"no sheet" Hermes text and H5, which D-016 dropped).
1. **IDs.** Canonical runtime IDs are the registry IDs `claude`, `codex`, `antigravity` (`agy`/`gemini` are aliases);
   persona IDs are `claude`, `codex`, `gemini`, `hermes`. Hermes is a **system persona** with no launchable adapter.
2. **Model has three fields per run:** `requestedModel` (task/route), `effectiveModel` (what the adapter actually
   passed; null when the adapter ignores model selection, e.g. antigravity today), `reportedModel` (what the CLI
   reported; codex reports none today). An ignored request is never shown as the model used.
3. **Run persistence is new work:** copy adapter result metadata into AgentRun.metadata and completion events, project
   it back, cover success/failure/cancel/restart, and add a bounded cross-job query for recent instances/models.
4. **D-009 end to end:** event binding, registry detail copying, both execution paths, a stable run<->execution link;
   an idle pooled resource carrying a previous identity is not an active instance; restored rows keep their rule.
5. **One role normalizer** before every guard: aliases builder/hardener/verifier -> build/harden/verify; canonical roles
   persisted; historical reads stay compatible indefinitely (input aliases for one release).
6. **Migrate every role producer first** (sprint specs, phase-order defaults in job_launcher, planner contracts and
   prompts, replanning, recovery) with explicit defaults for missing roles; only then reject unknown roles.
7. **New guards:** research = findings-path allowlist; scaffold = named-path allowlist; integration checks cover
   additions/deletions/renames. Post-hoc git checks are not a sandbox; "read-only" is documented as "no tracked changes
   outside the allowlist" unless runtime isolation is added. Citation completeness gets its own validator.
8. **Repair:** failed-task fallbacks inherit runtime/model/guard (D-011); task-linked verification repairs stay
   `build`; unlinked repairs use the sprint route.
9. **Routing lives in one shared resolver** (explicit task/phase > sprint > configured role defaults), used by
   launcher, planner, scheduler and sprint runner; the resolved route is persisted before execution. The Herdr default
   (D-016) must be implemented: current defaults are still subprocess.
10. **Keep operational capabilities** separate from presentation and reconcile them with routing (Claude's profile
    lacks `implementation`, so the build route would be re-routed today).
11. **Client migration:** LysControl adapter, types, views and fixtures migrate together before legacy fields are
    removed; the lysomarchy.hermes widget reads only /execution (additive fields are safe).
12. **Persona restrictions are structural:** only `voice` fields reach the prompt; behaviouralRules/systemPromptFragment
    from catalog data are not prompt-visible; provenance is validated by the loader; invented fallback prose and broken
    fallback constructors are removed. "Voice, not content" is enforced by never styling results, only display text.
13. **Order:** contracts (roles, routing, persona schema) -> H1 personas (may start once the schema restriction is in)
    -> H3 runs/events persistence -> H4 capability + readiness discovery (supports_agent is compatibility, not
    readiness) -> H2 /agents -> client migration -> remove legacy fields. Acceptance checks: restart/migration,
    alias-guard, routing-capability, client compatibility.

### Revision 3a (Codex r3: AGREE WITH CHANGES; items 7 and 9 tightened, notes on 2 and 12 accepted)
- **7. Guards.** For `research` and `scaffold`, the final worktree must have **no tracked or untracked changes outside
  the normalized allowlist** (git status including untracked files). Ignored, transient and outside-worktree writes are
  explicitly *not* covered unless runtime isolation is added; the guard is documented as such, not as a sandbox.
- **9. Routing configuration and fallback.**
  - Owner and location: Hermes, file `config/routing.json` in Hermes-lab (versioned); override schema
    `{"roles": {"<role>": {"runtime": "...", "model": "...", "backend": "..."}}}` at three levels: the config file
    defaults, a sprint spec `routing` object, and per-phase/task fields. Precedence: task/phase > sprint > config.
  - **Explicit choices fail closed:** if a task or sprint names a runtime/backend/model that is unsupported or
    unavailable, the task fails with a clear error; it is never silently rerouted.
  - **Defaults may fall back, visibly:** if a *config default* is unavailable (CLI missing, backend down), the resolver
    falls back to the next configured option for that role, else `subprocess`, and records `routeFallback` with the reason
    on the run and in events.
  - The scheduler may reroute only unassigned work; an explicitly assigned actor is kept or the task fails (consistent
    with D-011).
  - **Known limitation, recorded:** Herdr hosts all three runtimes, but only `claude` and `codex` pass a model selection;
    `antigravity` ignores `options.model` today, so its `effectiveModel` is null and the research route uses its runtime
    default model.
- **Note on 2.** When no model is requested, `effectiveModel` records the adapter's default (Claude: `sonnet`).
- **Note on 12.** Voice-only prompt fields keep artifacts, results and records unstyled and separate from display text;
  they do not guarantee that a persona's tone never influences generated content. That limit is accepted and stated.

### Revision 3b (Codex r3a: item 9)
- **Routes are ordered lists.** Config schema: `{"roles": {"<role>": [{"runtime": "...", "model": "...",
  "backend": "..."}, ...]}}`; the first entry is the default, later entries are fallbacks in order. A sprint `routing`
  object or a task/phase field replaces the list for its scope.
- **Fallback walks the list:** the resolver takes the first entry whose runtime CLI is ready, whose backend is available
  and supports that runtime (`supports_agent`), and, if a model is set, whose adapter can apply it. Each skipped entry is
  recorded in `routeFallback` with its reason.
- **`subprocess` is a fallback backend only, never a fix for a missing runtime:** it is tried for an entry only when that
  entry's runtime CLI is ready and only the requested backend is unavailable.
- **No viable route: fail clearly** with `FAILED_NO_ROUTE` and the list of reasons; nothing runs.
- Explicit task/sprint choices still fail closed without walking any fallback list.
