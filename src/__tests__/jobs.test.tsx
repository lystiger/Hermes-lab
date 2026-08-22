import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueueTable } from '../features/jobs/QueueTable';
import { Job } from '../api/types';

describe('Job Queue & Arbitrary Agent Reference', () => {
  it('renders a job with arbitrary/dynamic agent IDs without errors', async () => {
    const customJobs: Job[] = [
      {
        id: '#999',
        priority: 'P0',
        title: 'Arbitrary Subagent Task',
        repository: 'company/core-repo',
        assignedAgentIds: ['kimi', 'subagent-42', 'reviewer-8f92'],
        status: 'QUEUED',
        estimatedTokens: '15k',
        estimatedTime: '4 min'
      }
    ];

    render(<QueueTable jobs={customJobs} showFilters={false} />);

    expect(await screen.findByText('#999')).toBeInTheDocument();
    expect(screen.getByText('Arbitrary Subagent Task')).toBeInTheDocument();
    expect(screen.getByText('company/core-repo')).toBeInTheDocument();
    expect(screen.getByText('P0')).toBeInTheDocument();
    expect(screen.getByText('QUEUED')).toBeInTheDocument();
  });
});
