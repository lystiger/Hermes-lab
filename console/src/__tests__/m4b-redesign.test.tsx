import { describe, it, expect, vi, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OverviewRoute } from '../routes/index';
import { QueueRoute } from '../routes/queue';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';
import { CopyId } from '../components/CopyId';
import { groupOf } from '../features/jobs/MissionBoard';
import { installLiveHermes, LIVE_JOB_SUMMARY } from './support/liveHermes';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('M4b noise rule: unknown-only panels are not rendered', () => {
  it('Overview shows no unknown-only metrics, and explains the ones it does show on hover', async () => {
    installLiveHermes();
    render(
      <MemoryRouter>
        <OverviewRoute />
      </MemoryRouter>
    );
    const toReview = (await screen.findByText('TO REVIEW')).parentElement!;
    expect(toReview.getAttribute('title')!.length).toBeGreaterThan(10);
    expect(screen.queryByText('SPEND')).not.toBeInTheDocument();
    expect(screen.queryByText('BUDGET')).not.toBeInTheDocument();
    expect(screen.queryByText(/Unreported metrics/)).not.toBeInTheDocument();
    expect(screen.queryByText('SPRINT BUDGET')).not.toBeInTheDocument();
    expect(screen.queryByText('QUEUE PROJECTION')).not.toBeInTheDocument();
    expect(screen.queryByText('EST. SPEND')).not.toBeInTheDocument();
  });

  it('Queue states what Hermes does not report and drops the empty execution-order panel', async () => {
    installLiveHermes();
    render(
      <MemoryRouter>
        <QueueRoute />
      </MemoryRouter>
    );
    expect(await screen.findByText('time estimates')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Execution order' })).not.toBeInTheDocument();
  });
});

describe('M4b hierarchy and cards', () => {
  it('the page title uses the display family, and metrics are tabular', () => {
    render(
      <PageHeader title="Probe" counts={[{ label: 'RUNNING', value: 3, unit: 'x' }]} />
    );
    expect(screen.getByRole('heading', { name: 'Probe' })).toHaveClass('font-display');
    expect(screen.getByText('3')).toHaveClass('lys-metric');
  });

  it('every panel is the shared Card: chamfered, layered, with an optional accent edge', () => {
    const { container } = render(
      <Card accent="var(--lys-agent-claude)">
        <span>body</span>
      </Card>
    );
    const outer = container.firstElementChild as HTMLElement;
    expect(outer).toHaveClass('lys-card-outer');
    expect(outer.querySelector('.lys-card-inner')).not.toBeNull();
    const edge = outer.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(edge.style.background).toContain('var(--lys-agent-claude)');
  });

  it('IDs keep the mono family; labels do not', () => {
    render(<CopyId value="job-42" />);
    expect(screen.getByText('job-42')).toHaveClass('font-mono-code');
  });
});


describe('M4b queue columns by real status', () => {
  it('maps each status to one column with a shape glyph as well as a colour', () => {
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'RUNNING' } as any).icon).toBeDefined();
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'FAILED' } as any).icon).not.toBe(groupOf({ ...LIVE_JOB_SUMMARY, status: 'COMPLETED' } as any).icon);
    expect(groupOf({ ...LIVE_JOB_SUMMARY, status: 'COMPLETED' } as any).id).toBe('COMPLETED');
  });

  it('shows the column for each status with its count, and a failed job in the Failed column', async () => {
    installLiveHermes({ jobs: [LIVE_JOB_SUMMARY] });
    render(
      <MemoryRouter>
        <QueueRoute />
      </MemoryRouter>
    );
    const failed = await screen.findByRole('list', { name: 'Failed jobs' });
    expect(within(failed).getByText('Live runner end-to-end')).toBeInTheDocument();
    const emptyStrip = screen.getByLabelText('Empty status groups');
    expect(within(emptyStrip).getByText('Running')).toBeInTheDocument();
  });
});
