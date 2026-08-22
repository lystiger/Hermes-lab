import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { JobDetailView } from '../features/jobs/JobDetailView';
import { lysStackApi } from '../api/client';
import { Thread, Message } from '../api/types';

describe('Phase 5.1 Operational Messaging & Truthful Artifact Trust UI', () => {
  const mockThread: Thread = {
    id: 'thread_job_run_20260822_s04',
    jobId: 'run_20260822_s04',
    title: 'Sprint lab-s04',
    participants: [
      { id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF' },
      { id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B' },
      { id: 'codex', kind: 'agent', displayName: 'Codex', accentColor: '#3FB950' }
    ],
    createdAt: '2026-08-22T10:00:00Z',
    updatedAt: '2026-08-22T10:02:00Z'
  };

  const mockMessages: Message[] = [
    {
      id: 'msg_001',
      threadId: 'thread_job_run_20260822_s04',
      from: { id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF' },
      to: [{ id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B' }],
      kind: 'handoff',
      intent: 'review_request',
      text: 'BUILD implementation complete. Commit 8a21fc9. Please review scheduler/state changes.',
      jobId: 'run_20260822_s04',
      phaseId: 'phase-1-build',
      artifactRefs: [
        {
          id: 'art_commit_1',
          type: 'git_commit',
          label: 'BUILD commit (8a21fc9)',
          ref: '8a21fc987654321',
          trust: {
            status: 'not_applicable',
            kind: 'git_reference',
            scope: 'target_repository',
            detail: 'Git commit reference'
          }
        },
        {
          id: 'art_handoff_1',
          type: 'handoff',
          label: 'BUILD handoff (HANDOFF_BUILD.md)',
          ref: 'handoffs/01_builder_gemini.md',
          trust: {
            status: 'verified',
            kind: 'path_containment',
            scope: 'hermes_run_root',
            detail: 'Contained within Hermes run root'
          }
        },
        {
          id: 'art_unverified_1',
          type: 'log',
          label: 'External system log',
          ref: '../../etc/shadow',
          trust: {
            status: 'unverified',
            kind: 'path_containment',
            scope: 'external',
            detail: 'Path escapes allowed roots via traversal'
          }
        }
      ],
      createdAt: '2026-08-22T10:01:00Z'
    },
    {
      id: 'msg_002',
      threadId: 'thread_job_run_20260822_s04',
      from: { id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B' },
      to: [{ id: 'codex', kind: 'agent', displayName: 'Codex', accentColor: '#3FB950' }],
      kind: 'handoff',
      intent: 'verification_request',
      text: 'HARDEN complete. Found one race in state cleanup; fixed in 91cf33a.',
      jobId: 'run_20260822_s04',
      phaseId: 'phase-2-harden',
      artifactRefs: [
        {
          id: 'art_commit_2',
          type: 'git_commit',
          label: 'HARDEN commit (91cf33a)',
          ref: '91cf33a12345678',
          trust: {
            status: 'not_applicable',
            kind: 'git_reference',
            scope: 'target_repository',
            detail: 'Git commit reference'
          }
        }
      ],
      createdAt: '2026-08-22T10:01:45Z'
    }
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(lysStackApi, 'getThreads').mockResolvedValue([mockThread]);
    vi.spyOn(lysStackApi, 'getMessages').mockResolvedValue(mockMessages);
    vi.spyOn(lysStackApi, 'getAgents').mockResolvedValue([
      { id: 'gemini', displayName: 'Gemini', provider: 'Google', model: '2.5-pro', role: 'Builder', capabilities: [], status: 'IDLE' },
      { id: 'claude', displayName: 'Claude', provider: 'Anthropic', model: 'sonnet', role: 'Hardener', capabilities: [], status: 'RUNNING' }
    ]);
  });

  it('renders operational messages, dynamic senders, and intent chips', async () => {
    render(
      <OperationalThreadView
        jobId="run_20260822_s04"
        assignedAgentIds={['gemini', 'claude', 'codex']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/OPERATIONAL THREAD & HANDOFFS/i)).toBeInTheDocument();
      expect(screen.getByText(/BUILD implementation complete/i)).toBeInTheDocument();
      expect(screen.getByText(/HARDEN complete/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/HANDOFF · review_request/i)).toBeInTheDocument();
    expect(screen.getByText(/HANDOFF · verification_request/i)).toBeInTheDocument();
  });

  it('renders git commit reference without path containment claim', async () => {
    render(
      <OperationalThreadView
        jobId="run_20260822_s04"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/BUILD commit \(8a21fc9\)/i)).toBeInTheDocument();
    });

    const commitChip = screen.getByText(/BUILD commit \(8a21fc9\)/i);
    fireEvent.click(commitChip);

    expect(screen.getByText(/ARTIFACT METADATA INSPECTION/i)).toBeInTheDocument();
    expect(screen.getByText(/8a21fc987654321/i)).toBeInTheDocument();
    expect(screen.getByText(/GIT_COMMIT/i)).toBeInTheDocument();
    expect(screen.getByText(/GIT REFERENCE/i)).toBeInTheDocument();
    expect(screen.getByText(/Git commit reference/i)).toBeInTheDocument();
    expect(screen.queryByText(/Contained within Hermes run root/i)).not.toBeInTheDocument();
  });

  it('renders verified filesystem artifact with path containment wording', async () => {
    render(
      <OperationalThreadView
        jobId="run_20260822_s04"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/BUILD handoff \(HANDOFF_BUILD.md\)/i)).toBeInTheDocument();
    });

    const handoffChip = screen.getByText(/BUILD handoff \(HANDOFF_BUILD.md\)/i);
    fireEvent.click(handoffChip);

    expect(screen.getByText(/ARTIFACT METADATA INSPECTION/i)).toBeInTheDocument();
    expect(screen.getByText(/VERIFIED · PATH CONTAINED/i)).toBeInTheDocument();
    expect(screen.getByText(/Verified runtime artifact · Contained within Hermes run root/i)).toBeInTheDocument();
  });

  it('renders unverified artifact without false trust claims', async () => {
    render(
      <OperationalThreadView
        jobId="run_20260822_s04"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/External system log/i)).toBeInTheDocument();
    });

    const unverifiedChip = screen.getByText(/External system log/i);
    fireEvent.click(unverifiedChip);

    expect(screen.getByText(/ARTIFACT METADATA INSPECTION/i)).toBeInTheDocument();
    expect(screen.getByText(/^UNVERIFIED$/i)).toBeInTheDocument();
    expect(screen.getByText(/Path escapes allowed roots via traversal/i)).toBeInTheDocument();
    expect(screen.queryByText(/Verified runtime artifact/i)).not.toBeInTheDocument();
  });

  it('submits operator dispatch message to thread', async () => {
    const sendSpy = vi.spyOn(lysStackApi, 'sendMessage').mockResolvedValue({
      id: 'msg_op_new',
      threadId: 'thread_job_run_20260822_s04',
      from: { id: 'operator', kind: 'operator', displayName: 'Operator' },
      to: [{ id: 'claude', kind: 'agent', displayName: 'Claude' }],
      kind: 'operator',
      text: 'Please review mutex locks.',
      createdAt: '2026-08-22T10:02:30Z'
    });

    render(
      <OperationalThreadView
        jobId="run_20260822_s04"
        assignedAgentIds={['claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Send operational guidance into job thread/i)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/Send operational guidance into job thread/i);
    fireEvent.change(input, { target: { value: 'Please review mutex locks.' } });

    const dispatchBtn = screen.getByRole('button', { name: /DISPATCH/i });
    fireEvent.click(dispatchBtn);

    await waitFor(() => {
      expect(sendSpy).toHaveBeenCalledWith(
        'thread_job_run_20260822_s04',
        'Please review mutex locks.',
        ['claude'],
        'operator',
        'operator_note'
      );
    });
  });

  it('renders JobDetailView with integrated OperationalThreadView', async () => {
    vi.spyOn(lysStackApi, 'getJob').mockResolvedValue({
      id: 'run_20260822_s04',
      sprintId: 'lab-s04',
      title: 'Hermes Sprint lab-s04',
      repository: 'LysControl',
      branch: 'hermes/lab-s04/integration',
      status: 'RUNNING',
      assignedAgentIds: ['gemini', 'claude'],
      phases: [
        { id: 'p1', name: 'BUILD', order: 1, role: 'builder', agentId: 'gemini', status: 'SUCCEEDED' },
        { id: 'p2', name: 'HARDEN', order: 2, role: 'hardener', agentId: 'claude', status: 'RUNNING' }
      ],
      executionGraph: [],
      changedFiles: [],
      retryHistory: [],
      retriesUsed: 0,
      maxRetries: 3,
      tokenBreakdown: []
    });

    render(<JobDetailView jobId="run_20260822_s04" />);

    await waitFor(() => {
      expect(screen.getByText(/Hermes Sprint lab-s04/i)).toBeInTheDocument();
      expect(screen.getByText(/OPERATIONAL THREAD & HANDOFFS/i)).toBeInTheDocument();
      expect(screen.getByText(/BUILD implementation complete/i)).toBeInTheDocument();
    });
  });
});
