# LysControl M8: Model and Effort Selector — Builder Handoff

## Summary

Implemented agent model and effort selection support in LysControl. Operators can view each agent's configured model/effort, last used model/effort/source, and select from allowed models and valid agent-specific effort tiers to update runtime settings for subsequent phases.

---

## Files Changed

### Contracts, Types & Adapters
- [`src/api/types.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/types.ts): Added DTO interfaces and types for model configuration: `AgentEffort`, `LastUsedSource`, `AgentConfiguredModel`, `AgentLastUsedModel`, `AgentModelConfig`, `AgentModelsMap`, `SetAgentModelRequest`, `SetAgentModelResponse`.
- [`src/api/contracts.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/contracts.ts): Extended `HermesApi` contract with `getAgentModels(): Promise<AgentModelsMap>` and `setAgentModel(agentId: string, model: string, effort?: string | null): Promise<SetAgentModelResponse>`.
- [`src/api/adapters/httpAdapter.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/adapters/httpAdapter.ts): Implemented `getAgentModels()` (`GET /agents/models`) and `setAgentModel()` (`PUT /agents/{id}/model`), extracting server error messages (`detail`) on 400/404 and handling network failures via `HermesUnreachableError`.
- [`src/api/mock/models.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/mock/models.ts): Added mock model registry fixture adhering to architectural boundary (`architecture.test.ts`).
- [`src/api/adapters/mockAdapter.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/adapters/mockAdapter.ts): Implemented `getAgentModels()` and `setAgentModel()` with local mock state and validation against allowed list.
- [`src/api/hooks.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/api/hooks.ts): Added `useAgentModels()` hook backed by `useResource('agent-models', ...)`.

### Features & UI Components
- [`src/features/agents/AgentModelSelector.tsx`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/features/agents/AgentModelSelector.tsx): New model and effort selector component featuring:
  - Compact display with visually distinct **Configured** (solid border, badge for `CLI default` when unconfigured) and **Last used** (dashed border, source badge).
  - Model select populated strictly from server `allowed` list.
  - Effort select populated strictly from valid agent effort tiers:
    - Claude: `null` only (`—`)
    - Gemini / AGY: `null`, `low`, `medium`, `high`
    - Codex: `null`, `minimal`, `low`, `medium`, `high`, `xhigh`
  - Honest unknown handling: `—` and "CLI default" when unconfigured.
  - Informational note: "Applies to the next phase".
  - Save button: disabled until changed and valid, disabled in mock mode with tooltip explanation.
  - Error handling: preserves user selection on save error, surfaces server message in `ErrorState` with retry. No optimistic update.
  - Four states: loading, error with retry, empty ("No models"), data with freshness timestamp.
- [`src/features/agents/AgentDossier.tsx`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/features/agents/AgentDossier.tsx): Integrated `<AgentModelSelector agentId={agent.id} accent={accent} />` in the agent dossier workspace panel.

### Support & Tests
- [`src/__tests__/support/liveHermes.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/__tests__/support/liveHermes.ts): Added `/agents/models` and `PUT /agents/:id/model` routing and fixture defaults to liveHermes mock handler.
- [`src/__tests__/m8-models-adapter.test.ts`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/__tests__/m8-models-adapter.test.ts): Contract tests for HTTP and mock adapters testing JSON deserialization, null handling, 400 error body parsing, 404 handling, and network failure.
- [`src/__tests__/m8-agent-model-selector.test.tsx`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/__tests__/m8-agent-model-selector.test.tsx): Component tests for configured vs last used distinction, allowed options, effort options per agent, Save button state, refresh on success, error handling with selection preservation, and the 4 data states.
- [`src/__tests__/m8-agent-model-selector-mock.test.tsx`](file:///home/lystiger/hermes-worktrees/lyscontrol-m8/builder/src/__tests__/m8-agent-model-selector-mock.test.tsx): Component test verifying control and Save button are disabled in mock mode with tooltip.

---

## UI States

1. **Loading**: Shows `<LoadingState label="Agent models" />` while `/agents/models` request is in flight.
2. **Error**: Shows `<ErrorState label="Agent models" error={...} onRetry={refetch} />` with retry button on network or HTTP failure. Stale notices (`<StaleNotice />`) shown if background refresh fails while prior data is cached.
3. **Empty**: Shows `<EmptyState>No models</EmptyState>` (<= 5 words) if an agent has no entry or an empty `allowed` list.
4. **Data**:
   - Compact display of **Configured** (model, effort, or `—` + `CLI default`) and **Last used** (model, effort, source).
   - Dropdown selectors for Model and Effort.
   - Save button disabled until changed and valid.
   - "Applies to the next phase" note.
   - Live freshness indicator (`<Freshness at={updatedAt} />`).
5. **Save Error**: Shows inline `<ErrorState label="Model update" ... />` preserving user selection and showing exact server `detail`.
6. **Mock Mode**: Dropdowns and Save button disabled with `title="Model configuration is disabled in mock mode"`.

---

## Tests Added & Verification Results

### Tests Added
- `src/__tests__/m8-models-adapter.test.ts` (10 tests):
  - `GET /agents/models` with configured, allowed, lastUsed.
  - Handling of null configured, null default, null lastUsed, and source variations (`phase`, `config`, `cli-default`).
  - Network failure -> `HermesUnreachableError`.
  - HTTP 500 error handling.
  - `PUT /agents/{id}/model` sending model and effort payload -> 200 response.
  - Null effort handling.
  - 400 error body detail parsing and propagation.
  - 404 unknown agent error handling.
  - `MockHermesApi` get and set behavior and allowed model validation.
- `src/__tests__/m8-agent-model-selector.test.tsx` (10 tests):
  - Renders configured and last used distinctly.
  - Honest `—` and `CLI default` when nothing is configured.
  - Model dropdown options match server `allowed` list.
  - Effort dropdown options match agent constraints (Claude, Gemini, Codex).
  - Save disabled until changed and valid.
  - Successful save triggers refetch and updates configured view.
  - Error keeps user selection, prevents optimistic update, and displays server error message.
  - Loading state when initial fetch is pending.
  - Error state with retry when fetch fails.
  - Empty state when allowed list is empty.
- `src/__tests__/m8-agent-model-selector-mock.test.tsx` (1 test):
  - Mock mode disables controls and Save button with explanatory tooltip.

### Suite Results
- `npm run typecheck`: Passed (clean exit, 0 errors).
- `npm run lint`: Passed (clean exit, 0 problems).
- `npm test -- --run`: Passed (34 test files, 275 tests passed).
- `npm run build`: Passed (production client build succeeded).
- `no-placeholders.test.ts` & `architecture.test.ts`: Passed.

---

## Anything Not Done and Why

All requirements from the specification were implemented and verified. No items were skipped or left undone.
Git operations were not performed, in accordance with the constraint that Hermes owns Git.
