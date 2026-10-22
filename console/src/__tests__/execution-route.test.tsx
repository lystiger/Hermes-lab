import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';
// These tests exercise the mock fixtures, which are opt-in only (VITE_LYSCONTROL_MOCK=1).
vi.hoisted(() => {
  process.env.VITE_LYSCONTROL_MOCK = '1';
});
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ExecutionRoute from '../routes/execution';
import { hermesApi } from '../api/client';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { EMPTY_EXECUTION_VIEW } from '../stores/executionReducer';

describe('Execution route (mock fixtures)', () => {
  beforeAll(async () => {
    useExecutionStore.setState({ view: EMPTY_EXECUTION_VIEW, snapshotStatus: 'idle', buffer: null, latestRequest: 0 });
    await useExecutionStore.getState().refreshSnapshot();
    useConsoleStore.getState().setInitialEvents(await hermesApi.getTraceEvents(100));
  });

  beforeEach(() => {
    render(
      <MemoryRouter>
        <ExecutionRoute />
      </MemoryRouter>
    );
  });

  it('renders the backend strip with subprocess, herdr and openrig status', () => {
    expect(screen.getAllByText('subprocess').length).toBeGreaterThan(0);
    expect(screen.getAllByText('herdr').length).toBeGreaterThan(0);
    expect(screen.getAllByText('openrig').length).toBeGreaterThan(0);
    expect(screen.getAllByText('openrig').length).toBeGreaterThan(0);
  });

  it('labels mock data clearly', () => {
    expect(screen.getByText(/MOCK FIXTURES/)).toBeInTheDocument();
  });

  it('does not render a deployed seats section', () => {
    expect(screen.queryByText('Deployed seats')).not.toBeInTheDocument();
    expect(screen.queryAllByTestId('execution-resource')).toHaveLength(0);
  });

  it('renders the recent execution timeline from events', () => {
    expect(screen.getByText('Recent execution timeline')).toBeInTheDocument();
    expect(screen.getAllByTestId('execution-event').length).toBeGreaterThan(0);
  });
});
