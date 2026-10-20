import { describe, it, expect, vi, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { act, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ActiveExecutionCard } from '../features/jobs/ActiveExecutionCard';
import { hermesApi } from '../api/client';
import { useConsoleStore } from '../stores/useConsoleStore';
import { installLiveHermes, LIVE_JOB_SUMMARY } from './support/liveHermes';

const ACTIVE = { ...LIVE_JOB_SUMMARY, id: 'job-active-1', title: 'Active one', status: 'RUNNING' };
const PHASES = {
  id: 'job-active-1',
  title: 'Active one',
  status: 'RUNNING',
  executionGraph: [{ id: 'p1', phase: 'build-phase', state: 'RUNNING', task: 'build', meta: '' }]
};

function bump() {
  act(() => {
    useConsoleStore.setState({ jobRuntimeVersion: useConsoleStore.getState().jobRuntimeVersion + 1 });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('active execution: phase refresh errors are shown, not hidden', () => {
  it('a failed phase refresh after a good load keeps the phases and shows a stale notice with retry', async () => {
    installLiveHermes({ jobs: [ACTIVE] });
    const spy = vi.spyOn(hermesApi, 'getJob');
    spy.mockResolvedValueOnce(PHASES as any);
    spy.mockRejectedValueOnce(new Error('Hermes /jobs/job-active-1 returned HTTP 500: Internal Server Error'));

    render(
      <MemoryRouter>
        <ActiveExecutionCard />
      </MemoryRouter>
    );
    expect(await screen.findByText('build-phase')).toBeInTheDocument();

    bump();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Job phases refresh failed, showing last loaded data');
    expect(within(alert).getByRole('button', { name: 'retry' })).toBeInTheDocument();
    expect(screen.getByText('build-phase')).toBeInTheDocument();
  });

  it('a phase load that fails with nothing loaded shows the error, not an empty graph', async () => {
    installLiveHermes({ jobs: [ACTIVE] });
    vi.spyOn(hermesApi, 'getJob').mockRejectedValue(new Error('Hermes /jobs/job-active-1 returned HTTP 500: Internal Server Error'));

    render(
      <MemoryRouter>
        <ActiveExecutionCard />
      </MemoryRouter>
    );
    expect(await screen.findByText('Job phases failed')).toBeInTheDocument();
    expect(screen.queryByText('No phases reported for this job yet.')).not.toBeInTheDocument();
  });
});

describe('active execution: a stale job list is flagged even with no active job', () => {
  it('shows "No active execution" together with the stale warning and its error', async () => {
    installLiveHermes({ jobs: [{ ...LIVE_JOB_SUMMARY, status: 'COMPLETED' }] });
    render(
      <MemoryRouter>
        <ActiveExecutionCard />
      </MemoryRouter>
    );
    expect(await screen.findByText('No active execution')).toBeInTheDocument();

    vi.spyOn(hermesApi, 'getJobs').mockRejectedValueOnce(new Error('Hermes /jobs returned HTTP 500: Internal Server Error'));
    bump();
    expect(await screen.findByText(/Active execution refresh failed, showing last loaded data/)).toBeInTheDocument();
    expect(screen.getByText('No active execution')).toBeInTheDocument();
  });
});
