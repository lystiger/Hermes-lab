import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { OperationalThreadView } from '../features/messaging/OperationalThreadView';
import { Message } from '../api/types';

// Mock api hooks
vi.mock('../api/hooks', () => ({
  useThreads: vi.fn(() => ({
    threads: [{ id: 'thread_test_1', title: 'Test Thread', messageCount: 3 }],
    loading: false,
    refetch: vi.fn(),
  })),
  useMessages: vi.fn(() => ({
    messages: [
      {
        id: 'msg_del_01',
        threadId: 'thread_test_1',
        from: { id: 'gemini', kind: 'agent', displayName: 'Gemini' },
        to: [{ id: 'claude', kind: 'agent', displayName: 'Claude' }],
        kind: 'delegation',
        intent: 'task_request',
        text: 'Please review scheduler concurrency synchronization.',
        conversationId: 'conv_delegation_01',
        createdAt: '2026-08-22T20:00:00Z',
        metadata: {
          taskId: 'task_del_01',
          delegatedBy: 'gemini',
          requiredCapabilities: ['review.code', 'review.concurrency'],
        },
      } as Message,
      {
        id: 'msg_tool_01',
        threadId: 'thread_test_1',
        from: { id: 'tool.git.inspect', kind: 'tool', displayName: 'Git Inspector' },
        to: [{ id: 'claude', kind: 'agent', displayName: 'Claude' }],
        kind: 'tool_result',
        intent: 'tool_result',
        text: 'diff --git a/scheduler.py b/scheduler.py\n+ lock.acquire()',
        conversationId: 'conv_delegation_01',
        createdAt: '2026-08-22T20:01:00Z',
        metadata: {
          toolId: 'tool.git.inspect',
          status: 'success',
        },
      } as Message,
      {
        id: 'msg_sub_01',
        threadId: 'thread_test_1',
        from: { id: 'subagent_claude_1', kind: 'agent', displayName: 'Subagent (claude 1)' },
        to: [{ id: 'claude', kind: 'agent', displayName: 'Claude' }],
        kind: 'a2a',
        intent: 'task_result',
        text: 'Subagent completed memory inspection.',
        conversationId: 'conv_delegation_01',
        createdAt: '2026-08-22T20:02:00Z',
        metadata: {
          subagent: true,
          parentAgentId: 'claude',
        },
      } as Message,
    ],
    loading: false,
    refetch: vi.fn(),
  })),
  useAgents: vi.fn(() => ({
    agents: [],
    loading: false,
  })),
  useSendThreadMessage: vi.fn(() => ({
    sendMessage: vi.fn(),
    sending: false,
  })),
}));

// Mock console store
vi.mock('../stores/useConsoleStore', () => ({
  useConsoleStore: vi.fn(() => ({
    selectedAgentId: 'claude',
    setSelectedAgentId: vi.fn(),
  })),
}));

describe('Phase 7: Capability-Aware Delegation & Tool Messaging UI', () => {
  it('renders delegation messages with DELEGATION chip, delegatedBy, and required capabilities', () => {
    render(<OperationalThreadView threadId="thread_test_1" />);

    expect(screen.getByText(/DELEGATION · by gemini/i)).toBeInTheDocument();
    expect(screen.getByText(/req: review.code, review.concurrency/i)).toBeInTheDocument();
    expect(screen.getByText(/Please review scheduler concurrency synchronization/i)).toBeInTheDocument();
  });

  it('renders tool actor results cleanly with TOOL indicator and no anime card styling', () => {
    render(<OperationalThreadView threadId="thread_test_1" />);

    expect(screen.getByText(/⚙ TOOL/i)).toBeInTheDocument();
    expect(screen.getByText(/TOOL_RESULT · tool_result/i)).toBeInTheDocument();
    expect(screen.getByText(/lock\.acquire\(\)/i)).toBeInTheDocument();
  });

  it('renders ephemeral subagent messages with SUBAGENT indicator and parent info', () => {
    render(<OperationalThreadView threadId="thread_test_1" />);

    expect(screen.getByText(/SUBAGENT \(parent: claude\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Subagent completed memory inspection/i)).toBeInTheDocument();
  });
});
