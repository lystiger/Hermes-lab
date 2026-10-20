import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorState, StaleNotice } from '../components/DataStates';
import { JobFailure } from '../features/jobs/JobRealData';
import { JobDetail } from '../api/types';

describe('Event & error text clamp guard', () => {
  const long2k = 'E'.repeat(2000);

  it('clamps ErrorState message to 2 lines and preserves full text in title attribute', () => {
    render(<ErrorState label="Test Resource" error={new Error(long2k)} />);
    const msgEl = screen.getByTitle(long2k);
    expect(msgEl).toBeInTheDocument();
    expect(msgEl).toHaveClass('line-clamp-2');
    expect(msgEl.getAttribute('title')).toBe(long2k);
    expect(msgEl.getAttribute('title')!.length).toBe(2000);
  });

  it('clamps StaleNotice message to 2 lines and preserves full text in title attribute', () => {
    render(<StaleNotice label="Test Resource" error={new Error(long2k)} />);
    const expectedTitle = `Test Resource refresh failed, showing last loaded data: ${long2k}`;
    const noticeEl = screen.getByTitle(expectedTitle);
    expect(noticeEl).toBeInTheDocument();
    expect(noticeEl).toHaveClass('line-clamp-2');
    expect(noticeEl.getAttribute('title')).toBe(expectedTitle);
    expect(noticeEl.getAttribute('title')!.length).toBeGreaterThan(2000);
  });

  it('clamps JobFailure explanation lines to 2 lines with title tooltip for multi-paragraph prompts', () => {
    const jobWithLongError: JobDetail = {
      id: 'job-long-error',
      title: 'Failed Task with Long Prompt',
      repository: 'test/repo',
      branch: 'main',
      status: 'FAILED',
      assignedAgentIds: ['hermes'],
      priority: 'P0',
      executionGraph: [],
      errors: [long2k]
    };

    render(<JobFailure job={jobWithLongError} />);
    const lineEl = screen.getByTitle(long2k);
    expect(lineEl).toBeInTheDocument();
    expect(lineEl).toHaveClass('line-clamp-2');
    expect(lineEl.getAttribute('title')).toBe(long2k);
    expect(lineEl.getAttribute('title')!.length).toBe(2000);
  });
});
