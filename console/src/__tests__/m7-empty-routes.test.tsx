import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { hermesApi, isRealApiMode } from '../api/client';
import { OverviewRoute } from '../routes/index';
import { QueueRoute } from '../routes/queue';
import { AgentsListRoute } from '../routes/agents/index';
import { UsageRoute } from '../routes/usage';
import { EventsRoute } from '../routes/events';
import { ExecutionRoute } from '../routes/execution';
import { SettingsRoute } from '../routes/settings';
import { Sidebar } from '../components/Sidebar';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { EMPTY_EXECUTION_VIEW } from '../stores/executionReducer';

const invented = ['#142', 'VehicleStateStore', 'moveinmate', '$4.12', '58%', 'SIMULATED', '~37 min', 'v0.1.0', 'raise cap', 'alert(', 'Phase 4'];
const routes = [
  ['/', OverviewRoute, ['No active execution', 'No jobs', 'No events']],
  ['/queue', QueueRoute, ['No jobs', 'No recoverable jobs']],
  ['/agents', AgentsListRoute, ['No agents', 'No agent selected']],
  ['/usage', UsageRoute, ['No provider usage']],
  ['/events', EventsRoute, ['No events']],
  ['/execution', ExecutionRoute, ['No deployed seats', 'No execution events']],
  ['/settings', SettingsRoute, ['No execution backends reported.']]
] as const;

beforeEach(async () => {
  useConsoleStore.setState({ connectionStatus: 'DISCONNECTED', backendHealth: null, allEvents: [], eFilter: 'All', qFilter: 'All', activeModalJobId: null, agentRuntimeStatuses: {} });
  useExecutionStore.setState({ view: EMPTY_EXECUTION_VIEW, snapshotStatus: 'idle', buffer: null, latestRequest: 0, snapshotLoadedAt: null });
  vi.spyOn(hermesApi, 'getHealth').mockResolvedValue({ status: 'ok', service: 'hermes', version: '9.9.9', uptimeSeconds: 0, timestamp: '2026-10-19T00:00:00Z' });
  for (const method of ['getAgents', 'getJobs', 'getRecoverableJobs', 'getPipeline', 'getTraceEvents', 'getProjections', 'getThreads'] as const) {
    vi.spyOn(hermesApi, method).mockResolvedValue([]);
  }
  vi.spyOn(hermesApi, 'getTelemetry').mockResolvedValue({ runningJobsCount: 0, queuedJobsCount: 0, blockedJobsCount: 0, failed24hCount: 0, sampleSize: 0, tokensToday: '—', estSpendToday: '—', sprintBudgetUsedPct: null });
  vi.spyOn(hermesApi, 'getCapacityTelemetry').mockResolvedValue({ providers: [], summary: null, jobsTracked: 0, timestamp: '2026-10-19T00:00:00Z' });
  vi.spyOn(hermesApi, 'getSettings').mockResolvedValue({ runtime: [], policy: [] });
  vi.spyOn(hermesApi, 'getExecutionSnapshot').mockResolvedValue({ backends: [], resources: [], openrig: null, takenAt: 0 });
  // Layout owns the snapshot loader; route components only consume its store.
  await hermesApi.getHealth();
  await useExecutionStore.getState().refreshSnapshot();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// Honest not-reported tooltips and the single measurement-window qualifier are
// explanatory copy, not invented values. Only rendered visible copy is checked.
function visibleText(container: HTMLElement) {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('.invisible, [hidden], [aria-hidden="true"]').forEach((node) => node.remove());
  return copy.textContent ?? '';
}

describe('M7 HTTP-mode empty routes while disconnected', () => {
  for (const [path, Component, emptyStates] of routes) {
    it(`${path}: no invented values or connected claims`, async () => {
      expect(isRealApiMode).toBe(true);
      const { container } = render(<MemoryRouter initialEntries={[path]}><Sidebar /><Component /></MemoryRouter>);
      await waitFor(() => expect(hermesApi.getExecutionSnapshot).toHaveBeenCalled());
      await waitFor(() => expect(container.textContent).not.toMatch(/Loading|Waiting for the execution snapshot/));
      const text = visibleText(container);
      expect(invented.filter((value) => text.includes(value))).toEqual([]);
      expect(text).not.toMatch(/\b(?:Online|Connected)\b/);
      expect(text.split('Not reported by Hermes').length - 1).toBeLessThanOrEqual(1);
      expect(text.split('since runtime start (process').length - 1).toBeLessThanOrEqual(1);
      expect(useConsoleStore.getState().connectionStatus).toBe('DISCONNECTED');
    });
    it(`${path}: explicit empty states use at most five words`, async () => {
      render(<MemoryRouter initialEntries={[path]}><Component /></MemoryRouter>);
      for (const label of emptyStates) {
        const matches = await screen.findAllByText(label);
        expect(matches.length).toBeGreaterThan(0);
        for (const match of matches) expect(match.textContent!.trim().split(/\s+/).length).toBeLessThanOrEqual(5);
      }
    });
  }
});
