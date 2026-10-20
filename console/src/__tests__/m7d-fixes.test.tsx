import { afterEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => { delete process.env.VITE_LYSCONTROL_MOCK; });

import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HttpHermesApi, mapJobSummary, TERMINAL_JOB_STATUSES } from '../api/adapters/httpAdapter';
import { JobStatus } from '../api/types';
import { groupOf } from '../features/jobs/MissionBoard';
import { ExecutionResourceCard } from '../features/execution/ExecutionResourceCard';
import { OverviewRoute } from '../routes/index';
import { installLiveHermes, LIVE_JOB_SUMMARY } from './support/liveHermes';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const cases: [JobStatus, string][] = [
  ['CREATED', 'QUEUED'], ['PLANNING', 'RUNNING'], ['EXECUTING', 'RUNNING'],
  ['WAITING_FOR_CAPACITY', 'QUEUED'], ['VERIFYING', 'RUNNING'], ['REPAIRING', 'RUNNING'],
  ['COMPLETED', 'COMPLETED'], ['BLOCKED', 'BLOCKED'], ['FAILED', 'FAILED'],
  ['CANCELLED', 'CANCELLED'], ['RUNNING', 'RUNNING'], ['PREPARING', 'RUNNING'],
  ['QUEUED', 'QUEUED'], ['CLAIMED', 'QUEUED']
];

describe('M7d real job statuses', () => {
  it.each(cases)('%s belongs to %s and produces matching telemetry', async (status, group) => {
    const job = { ...LIVE_JOB_SUMMARY, status, completedAt: new Date().toISOString() };
    expect(groupOf(mapJobSummary(job)).id).toBe(group);
    expect(TERMINAL_JOB_STATUSES.includes(status)).toBe(['COMPLETED', 'FAILED', 'CANCELLED'].includes(status));
    installLiveHermes({ jobs: [job] });
    const telemetry = await new HttpHermesApi('http://localhost:8000').getTelemetry();
    expect(telemetry).toMatchObject({
      runningJobsCount: group === 'RUNNING' ? 1 : 0,
      queuedJobsCount: group === 'QUEUED' ? 1 : 0,
      blockedJobsCount: group === 'BLOCKED' ? 1 : 0,
      failed24hCount: group === 'FAILED' ? 1 : 0
    });
  });

  it('preserves the raw text of an unknown status', () => {
    expect(groupOf(mapJobSummary({ ...LIVE_JOB_SUMMARY, status: 'FUTURE_STATUS' })))
      .toMatchObject({ id: 'OTHER:FUTURE_STATUS', label: 'Other · FUTURE_STATUS' });
  });

  it('shows EXECUTING in Overview active execution', async () => {
    installLiveHermes({ jobs: [{ ...LIVE_JOB_SUMMARY, status: 'EXECUTING' }] });
    render(<MemoryRouter><OverviewRoute /></MemoryRouter>);
    const card = await screen.findByLabelText('Active execution');
    expect(await within(card).findByText('EXECUTING')).toBeInTheDocument();
    expect(within(card).queryByText('No active execution')).not.toBeInTheDocument();
  });
});

it('stacks long job and task IDs with truncation and full tooltips', () => {
  const jobId = 'job-' + 'a'.repeat(100);
  const taskId = 'task-' + 'b'.repeat(100);
  render(<ExecutionResourceCard resource={{
    backend: 'openrig', kind: 'seat', id: 'seat-1', label: 'Seat', state: 'running',
    jobId, taskId, executionId: null, since: '2026-10-19T00:00:00Z', expiresAt: null, details: {}
  }} nowMs={Date.now()} />);
  const job = screen.getByTitle(jobId);
  const task = screen.getByTitle(taskId);
  expect(job).toHaveClass('truncate');
  expect(task).toHaveClass('truncate');
  expect(job.parentElement).toBe(task.parentElement);
  expect(job.parentElement).toHaveClass('flex-col', 'min-w-0');
});
