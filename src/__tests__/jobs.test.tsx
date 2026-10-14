import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueueTable } from '../features/jobs/QueueTable';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { Job, JobDetail } from '../api/types';
import * as hooks from '../api/hooks';

describe('Job Queue & Arbitrary Agent Reference', () => {
  it('renders a job with arbitrary/dynamic agent IDs without errors', async () => {
    const customJobs: Job[] = [
      {
        id: 'run_20260822_unigreen_01',
        priority: 'P0',
        title: 'Unigreen Inquiry Delivery',
        repository: 'Unigreen',
        branch: 'hermes/unigreen-inquiry-v1/integration',
        assignedAgentIds: ['gemini', 'claude', 'codex', 'reviewer-8f92'],
        status: 'RUNNING',
        estimatedTokens: '—',
        estimatedTime: '—'
      }
    ];

    render(<QueueTable jobs={customJobs} showFilters={false} />);

    expect(await screen.findByText('run_20260822_unigreen_01')).toBeInTheDocument();
    expect(screen.getByText('Unigreen Inquiry Delivery')).toBeInTheDocument();
    expect(screen.getByText('Unigreen')).toBeInTheDocument();
    expect(screen.getByText('P0')).toBeInTheDocument();
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('renders generic data-driven phases and artifacts in JobDetailView without static assumptions', async () => {
    const mockDetail: JobDetail = {
      id: 'run_custom_sprint_99',
      sprintId: 'custom-sprint-99',
      title: 'Custom Multi-Step Sprint',
      repository: 'Unigreen/Core',
      branch: 'hermes/custom-sprint/integration',
      priority: 'P1',
      status: 'RUNNING',
      assignedAgentIds: ['gemini', 'claude', 'codex'],
      phases: [
        { id: 'p1', name: 'RESEARCH_PHASE', order: 1, role: 'researcher', agentId: 'gemini', status: 'SUCCEEDED', commitSha: 'sha111' },
        { id: 'p2', name: 'ARCH_REVIEW', order: 2, role: 'reviewer', agentId: 'claude', status: 'RUNNING' },
        { id: 'p3', name: 'FUZZ_TESTING', order: 3, role: 'fuzzer', agentId: 'codex', status: 'PENDING' }
      ],
      executionGraph: [],
      changedFiles: [],
      retryHistory: [],
      retriesUsed: 0,
      maxRetries: 3,
      tokenBreakdown: [],
      artifacts: [
        { id: 'art_1', type: 'git_commit', label: 'Commit (sha111)', ref: 'sha111222' }
      ]
    };

    vi.spyOn(hooks, 'useJob').mockReturnValue({
      job: mockDetail,
      loading: false,
      error: null,
      updatedAt: null,
      refetch: vi.fn()
    });

    render(
      <MemoryRouter>
        <JobDetailView jobId="run_custom_sprint_99" />
      </MemoryRouter>
    );

    expect(await screen.findByText('run_custom_sprint_99')).toBeInTheDocument();
    expect(screen.getByText('Custom Multi-Step Sprint')).toBeInTheDocument();
    expect(screen.getByText('RESEARCH_PHASE')).toBeInTheDocument();
    expect(screen.getByText('ARCH_REVIEW')).toBeInTheDocument();
    expect(screen.getByText('FUZZ_TESTING')).toBeInTheDocument();
    expect(screen.getByText('Commit (sha111)')).toBeInTheDocument();
  });
});
