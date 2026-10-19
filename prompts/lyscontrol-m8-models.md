# Role: BUILDER — LysControl M8: model and effort selector

You are the BUILDER. Hermes owns Git: do not run git add, commit, merge, push,
reset, checkout, or alter Git metadata. Work only in your assigned worktree.
Run `npm ci` first. Use only `npm ci`, `npm run typecheck`, `npm run lint`,
`npm test`, `npm run build`. Do not start servers.

Read `docs/console-spec.md` (real data only, unknown stays `—`, four states for
every data view, no fake actions), then `src/features/agents/AgentDossier.tsx`,
`src/api/contracts.ts`, `src/api/adapters/httpAdapter.ts`, `src/api/adapters/mockAdapter.ts`,
`src/api/hooks.ts` (see `useResource`), `src/components/DataStates.tsx` and
`src/__tests__/architecture.test.ts`.

## What to build

Hermes now owns a model registry. Add a model and effort selector to each
agent's dossier (the Agents page) so the operator can see and change which
model an agent will use.

### Hermes API (live now at VITE_LYSSTACK_API_URL, default http://localhost:8000)

`GET /agents/models` → object keyed by agent id (`gemini`, `claude`, `codex`),
each:

```json
{"configured": {"default": "gpt-6.1-sol", "effort": "low"},
 "allowed": ["gpt-5-codex", "gpt-5.4", "gpt-5.3-codex", "gpt-6.1-sol"],
 "lastUsed": {"model": "sonnet", "effort": null, "source": "phase"}}
```

`configured.default` and `lastUsed` can be null. `lastUsed.source` is `phase`,
`config` or `cli-default`. Effort values: Claude accepts null only; Codex null,
minimal, low, medium, high, xhigh; Gemini (agy) null, low, medium, high.

`PUT /agents/{id}/model` with `{"model": "<from allowed>", "effort": null|"low"|…}`
→ 200 `{"default": "...", "effort": "..."}`; 400 `{"detail": "..."}` if the
model or effort is not allowed; 404 for an unknown agent. Omitting effort
resets it to null.

### UI rules

- Extend the `HermesApi` contract with `getAgentModels()` and
  `setAgentModel(agentId, model, effort)`. Implement both in the HTTP adapter
  and the mock adapter (mock data stays in `api/mock`; UI code must not import
  it, `architecture.test.ts` enforces that). Add DTO types.
- Dossier shows, in a compact block: **Configured** (model, effort), **Last
  used** (model, effort, source) and a model select plus an effort select
  built only from the `allowed` list and the effort values valid for that
  agent. Never accept free text.
- Honest: when nothing is configured show `—` and "CLI default"; configured and
  last used are different things and must stay visually distinct; show
  "Applies to the next phase" once, as a tooltip or one short line.
- Saving: a Save button (disabled until changed and valid); on success refresh
  from the server and show an updated stamp; on 400/404/network error show the
  server's message in the standard error state and keep the user's selection.
  No optimistic update.
- Four states like every data view: loading, error with retry, empty ("No
  models" at most 5 words), data with freshness time. Use the shared
  `DataStates` components and `useResource`.
- Keep copy short: labels 1-3 words, no explanatory paragraphs. Use the existing
  card, tokens and `PageHeader` conventions; no raw hex colors.
- Keyboard accessible, visible focus, labelled controls.
- Real mode only for writing: in mock mode the control is disabled with a
  tooltip saying why.

### Tests

- Adapter contract tests with the JSON above (including nulls and the 400
  error body).
- Component tests: renders configured and last used distinctly; options come
  from `allowed`; effort options depend on the agent; Save disabled until
  changed; success refreshes; error keeps the selection and shows the message;
  mock mode disables the control.
- `no-placeholders.test.ts` and `architecture.test.ts` must keep passing.

## Constraints

No new runtime dependency. Do not change other pages. Keep routes. Do not
reintroduce demo data.

## Done means

typecheck, lint, test and build pass. Write `HANDOFF_MODELS.md`: files changed,
the UI states, tests added, anything not done and why. Stop after the handoff.
