/**
 * Client for the orchestrator chat. Chat and draft only: the API has no route that starts or
 * cancels a run, so this client has none either.
 */

import type { ChatUsage } from '../features/comms/contextUsage';

const apiUrl = import.meta.env.VITE_LYSSTACK_API_URL || 'http://localhost:8000';

export interface OrchestratorOptions {
  providers: { id: string; models: string[]; efforts: string[] }[];
}

export interface OrchestratorMessage {
  role: 'user' | 'assistant';
  content: string;
  drafts?: string[];
  at: string;
}

export interface OrchestratorConversation {
  id: string;
  title: string;
  model: string;
  effort: string | null;
  system_commit: string;
  created: string;
  messages: OrchestratorMessage[];
  usage?: ChatUsage | null;
  summary?: string | null;
  summary_upto?: number;
}

export type OrchestratorConversationSummary = Omit<OrchestratorConversation, 'messages'>;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // keep the status code as the message
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const orchestratorApi = {
  options: () => request<OrchestratorOptions>('/orchestrator/options'),
  listConversations: () => request<OrchestratorConversationSummary[]>('/orchestrator/conversations'),
  getConversation: (id: string) => request<OrchestratorConversation>(`/orchestrator/conversations/${id}`),
  createConversation: (model: string, effort: string | null) =>
    request<OrchestratorConversation>('/orchestrator/conversations', {
      method: 'POST',
      body: JSON.stringify({ model, effort }),
    }),
  updateConversation: (id: string, body: { title?: string; model?: string; effort?: string | null }) =>
    request<OrchestratorConversationSummary>(`/orchestrator/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteConversation: async (id: string): Promise<void> => {
    await request<void>(`/orchestrator/conversations/${id}`, { method: 'DELETE' });
  },
  compactConversation: (id: string) =>
    request<OrchestratorConversationSummary>(`/orchestrator/conversations/${id}/compact`, { method: 'POST' }),
  sendMessage: (id: string, content: string) =>
    request<OrchestratorMessage>(`/orchestrator/conversations/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
};
