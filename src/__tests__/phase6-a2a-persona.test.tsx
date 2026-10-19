import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { hermesApi } from '../api/client';
import { Thread, Message, AgentSummary } from '../api/types';

describe('Phase 6 Generic Agent Identity, Personas & A2A Conversations UI', () => {
  const mockThread: Thread = {
    id: 'thread_job_run_p6_001',
    jobId: 'run_p6_001',
    title: 'Phase 6 Sprint Execution',
    participants: [
      { id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF', subtitle: 'Energetic Builder' },
      { id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B', subtitle: 'Calm Hardener' },
      { id: 'custom-agent', kind: 'agent', displayName: 'Custom Agent', accentColor: '#A78BFA', subtitle: 'Dynamic Planner' }
    ],
    createdAt: '2026-08-22T12:00:00Z',
    updatedAt: '2026-08-22T12:05:00Z'
  };

  const mockAgents: AgentSummary[] = [
    {
      id: 'gemini',
      displayName: 'Gemini',
      provider: 'Google AI Studio',
      model: 'antigravity-2.5-pro',
      role: 'Implementation & Scaffolding',
      capabilities: ['build'],
      status: 'IDLE',
      presentation: {
        displayName: 'Gemini',
        accentColor: '#5B8CFF',
        subtitle: 'Energetic Builder',
        sigil: 'BUILD'
      }
    },
    {
      id: 'claude',
      displayName: 'Claude',
      provider: 'Anthropic API',
      model: 'claude-sonnet-4-5',
      role: 'Architecture & Hardening',
      capabilities: ['harden'],
      status: 'RUNNING',
      presentation: {
        displayName: 'Claude',
        accentColor: '#D9A05B',
        subtitle: 'Calm Hardener',
        sigil: 'HARDEN'
      }
    },
    {
      id: 'custom-agent',
      displayName: 'Custom Agent',
      provider: 'Custom AI',
      model: 'custom-agent-v1',
      role: 'Dynamic Planning',
      capabilities: ['planning'],
      status: 'IDLE',
      presentation: {
        displayName: 'Custom Agent',
        accentColor: '#A78BFA',
        subtitle: 'Dynamic Planner',
        sigil: 'PLAN'
      }
    }
  ];

  const mockMessages: Message[] = [
    {
      id: 'msg_p6_001',
      threadId: 'thread_job_run_p6_001',
      from: { id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF', subtitle: 'Energetic Builder' },
      to: [{ id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B', subtitle: 'Calm Hardener' }],
      kind: 'a2a',
      intent: 'review_request',
      conversationId: 'conv_scheduler_review',
      text: 'BUILD complete. Please review scheduler state mutex locking.',
      createdAt: '2026-08-22T12:01:00Z'
    },
    {
      id: 'msg_p6_002',
      threadId: 'thread_job_run_p6_001',
      from: { id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B', subtitle: 'Calm Hardener' },
      to: [{ id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF', subtitle: 'Energetic Builder' }],
      kind: 'a2a',
      intent: 'correction_request',
      conversationId: 'conv_scheduler_review',
      replyTo: 'msg_p6_001',
      correlationId: 'corr_review_01',
      text: 'Found race condition in reset_state(). Please acquire state mutex before flush.',
      createdAt: '2026-08-22T12:02:00Z'
    },
    {
      id: 'msg_p6_003',
      threadId: 'thread_job_run_p6_001',
      from: { id: 'gemini', kind: 'agent', displayName: 'Gemini', accentColor: '#5B8CFF', subtitle: 'Energetic Builder' },
      to: [{ id: 'claude', kind: 'agent', displayName: 'Claude', accentColor: '#D9A05B', subtitle: 'Calm Hardener' }],
      kind: 'a2a',
      intent: 'correction_result',
      conversationId: 'conv_scheduler_review',
      replyTo: 'msg_p6_002',
      correlationId: 'corr_review_01',
      text: 'Resolved in commit 91cf33a. Mutex is now acquired prior to reset_state().',
      createdAt: '2026-08-22T12:03:00Z'
    },
    {
      id: 'msg_p6_004',
      threadId: 'thread_job_run_p6_001',
      from: { id: 'custom-agent', kind: 'agent', displayName: 'Custom Agent', accentColor: '#A78BFA', subtitle: 'Dynamic Planner' },
      to: [{ id: 'gemini', kind: 'agent', displayName: 'Gemini' }],
      kind: 'a2a',
      intent: 'question',
      conversationId: 'conv_planning_sync',
      text: 'Are next sprint dependencies prepared for migration batch?',
      createdAt: '2026-08-22T12:04:00Z'
    }
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hermesApi, 'getThreads').mockResolvedValue([mockThread]);
    vi.spyOn(hermesApi, 'getMessages').mockResolvedValue(mockMessages);
    vi.spyOn(hermesApi, 'getAgents').mockResolvedValue(mockAgents);
  });

  it('renders persona subtitles and generic open-string agent identities without breaking', async () => {
    render(
      <OperationalThreadView
        jobId="run_p6_001"
        assignedAgentIds={['gemini', 'claude', 'custom-agent']}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Gemini').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Claude').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Custom Agent').length).toBeGreaterThan(0);
    });

    // Check persona subtitles
    expect(screen.getAllByText('Energetic Builder').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Calm Hardener').length).toBeGreaterThan(0);
    expect(screen.getByText('Dynamic Planner')).toBeInTheDocument();
  });

  it('renders conversation tags, replyTo links, and correlation IDs', async () => {
    render(
      <OperationalThreadView
        jobId="run_p6_001"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Found race condition in reset_state/i)).toBeInTheDocument();
    });

    // Conversation tags
    expect(screen.getAllByText('conv_scheduler_review').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText('conv_planning_sync').length).toBeGreaterThan(0);

    // Reply-To badges
    expect(screen.getByText('reply: msg_p6_001')).toBeInTheDocument();
    expect(screen.getByText('reply: msg_p6_002')).toBeInTheDocument();

    // Correlation ID
    expect(screen.getAllByText('corr:corr_review_01').length).toBe(2);
  });

  it('filters messages by conversation ID selector', async () => {
    render(
      <OperationalThreadView
        jobId="run_p6_001"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Found race condition in reset_state/i)).toBeInTheDocument();
      expect(screen.getByText(/Are next sprint dependencies prepared/i)).toBeInTheDocument();
    });

    // Select conv_planning_sync
    const convSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(convSelect, { target: { value: 'conv_planning_sync' } });

    await waitFor(() => {
      expect(screen.getByText(/Are next sprint dependencies prepared/i)).toBeInTheDocument();
      expect(screen.queryByText(/Found race condition in reset_state/i)).not.toBeInTheDocument();
    });
  });

  it('supports replying to a specific message from UI', async () => {
    render(
      <OperationalThreadView
        jobId="run_p6_001"
        assignedAgentIds={['gemini', 'claude']}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByTitle('Reply to this message').length).toBeGreaterThan(0);
    });

    const replyButtons = screen.getAllByTitle('Reply to this message');
    fireEvent.click(replyButtons[1]); // Reply to Claude's message (msg_p6_002)

    expect(screen.getByText(/Replying to msg_p6_002/)).toBeInTheDocument();
  });
});
