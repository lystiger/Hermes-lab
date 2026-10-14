import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { JobDetail, TraceEvent } from '../api/types';
import * as hooks from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { viewFromSnapshot } from '../stores/executionReducer';
import { createMockExecutionSnapshot } from '../api/mock/execution';

const JOB: JobDetail = {
  id: 'job-142',
  title: 'Redis state refactor',
  repository: 'moveinmate/backend',
  status: 'RUNNING',
  assignedAgentIds: ['claude'],
  executionGraph: [],
  changedFiles: [],
  retryHistory: [],
  retriesUsed: 0,
  maxRetries: 3,
  tokenBreakdown: []
};

const execEvent: TraceEvent = {
  id: 'evt-badge-1',
  ts: '10:42:31.000',
  rawTs: 37351,
  source: { id: 'openrig', kind: 'runtime', displayName: 'OpenRig' },
  kind: 'execution.resource_acquired',
  detail: 'reviewer-2 acquired · reused',
  dur: '—',
  jobId: 'job-142',
  taskId: 'task-142-verify',
  metadata: {
    backend: 'openrig',
    executionId: 'exec-142-verify-2',
    resource: { kind: 'seat', id: 'seat-reviewer-2', label: 'reviewer-2' },
    reused: true
  }
};

describe('JobDetailView backend badge (D-009)', () => {
  beforeEach(() => {
    vi.spyOn(hooks, 'useJob').mockReturnValue({ job: JOB, loading: false, error: null, updatedAt: null, refetch: vi.fn() });
    useConsoleStore.setState({ allEvents: [execEvent], activeModalJobId: 'job-142' });
    // Live resource state comes from the execution snapshot.
    useExecutionStore.setState({
      view: viewFromSnapshot(createMockExecutionSnapshot()),
      snapshotStatus: 'ready',
      buffer: null,
      latestRequest: 0
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the task backend and resource badge, linking to the Execution page', () => {
    render(
      <MemoryRouter>
        <JobDetailView jobId="job-142" />
      </MemoryRouter>
    );

    expect(screen.getByText('task-142-verify')).toBeInTheDocument();
    const link = screen.getByTestId('job-task-execution');
    expect(link).toHaveAttribute('href', '/execution');
    expect(within(link).getByText('openrig')).toBeInTheDocument();
    expect(within(link).getByText('reviewer-2')).toBeInTheDocument();
    expect(within(link).getByText('reused')).toBeInTheDocument();
    expect(within(link).getByText('running')).toBeInTheDocument();
  });

  it('says so when a job has no backend execution yet', () => {
    useConsoleStore.setState({ allEvents: [] });
    render(
      <MemoryRouter>
        <JobDetailView jobId="job-142" />
      </MemoryRouter>
    );
    expect(screen.getByText('No backend execution recorded for this job yet.')).toBeInTheDocument();
  });

  it('a seat reused by a later task never relabels the earlier task', () => {
    const seat = { kind: 'seat', id: '01SEAT', label: 'worker' };
    const ev = (id: string, rawTs: number, taskId: string, executionId: string, kind: string, extra = {}) => ({
      id, ts: '10:00:00.000', rawTs, source: { id: 'openrig', kind: 'runtime', displayName: 'OpenRig' },
      kind, detail: '', dur: '—', jobId: 'job-142', taskId,
      metadata: { backend: 'openrig', executionId, resource: seat, ...extra }
    }) as TraceEvent;
    useConsoleStore.setState({
      allEvents: [
        ev('t1-fin', 10, 'T1', 'exec-1', 'execution.finished'),
        ev('t2-acq', 20, 'T2', 'exec-2', 'execution.resource_acquired', { reused: true })
      ]
    });
    // The live seat now belongs to T2's execution and is running.
    useExecutionStore.setState({
      view: viewFromSnapshot({
        backends: [], openrig: null,
        resources: [{
          backend: 'openrig', kind: 'seat', id: '01SEAT', label: 'worker', state: 'running',
          jobId: 'job-142', taskId: 'T2', executionId: 'exec-2', since: '2026-10-14T00:00:00Z',
          expiresAt: null, details: { reused: true }
        }]
      })
    });

    render(
      <MemoryRouter>
        <JobDetailView jobId="job-142" />
      </MemoryRouter>
    );

    const [t2, t1] = screen.getAllByTestId('job-task-execution');
    expect(within(t2).getByText('T2')).toBeInTheDocument();
    expect(within(t2).getByText('running')).toBeInTheDocument();
    expect(within(t2).getByText('reused')).toBeInTheDocument();
    expect(within(t1).getByText('T1')).toBeInTheDocument();
    expect(within(t1).getByText('finished')).toBeInTheDocument();
    expect(within(t1).queryByText('reused')).toBeNull();
    expect(within(t1).queryByText('running')).toBeNull();
  });
});
