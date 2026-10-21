import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  options: vi.fn(),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  createConversation: vi.fn(),
  sendMessage: vi.fn(),
}));

vi.mock('../api/orchestrator', () => ({ orchestratorApi: api }));

import { CommsRoute } from '../routes/comms';

const conversation = {
  id: 'abc123def456',
  title: 'New orchestrator chat',
  model: 'claude-sonnet-5-5',
  effort: null,
  system_commit: '0123456789abcdef',
  created: '2026-10-21T10:00:00+0700',
  messages: [],
};

beforeEach(() => {
  api.options.mockResolvedValue({
    providers: [{ id: 'claude', models: ['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5'], efforts: ['low', 'high'] }],
  });
  api.listConversations.mockResolvedValue([]);
  api.createConversation.mockResolvedValue(conversation);
  api.getConversation.mockResolvedValue(conversation);
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function renderRoute() {
  return render(
    <MemoryRouter>
      <CommsRoute />
    </MemoryRouter>,
  );
}

function composer() {
  return screen.getByLabelText('Message') as HTMLTextAreaElement;
}

describe('Comms chat', () => {
  it('offers the models the API reports and a note that the chat cannot act', async () => {
    renderRoute();

    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Model' })).toBeInTheDocument());
    const model = screen.getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    expect([...model.options].map((o) => o.value)).toEqual(['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5']);
    expect(screen.getByText(/Type a message to start a chat/)).toBeInTheDocument();
  });

  it('sends on Enter and starts a chat with the chosen model when none is open', async () => {
    api.sendMessage.mockResolvedValue({ role: 'assistant', content: 'hi', drafts: [], at: '' });
    api.getConversation.mockResolvedValue({ ...conversation, messages: [{ role: 'user', content: 'hello', at: '' }, { role: 'assistant', content: 'hi', drafts: [], at: '' }] });
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('combobox', { name: 'Model' }), { target: { value: 'claude-opus-5-5' } });

    fireEvent.change(composer(), { target: { value: 'hello' } });
    fireEvent.keyDown(composer(), { key: 'Enter' });

    await waitFor(() => expect(api.createConversation).toHaveBeenCalledWith('claude-opus-5-5', null));
    await waitFor(() => expect(api.sendMessage).toHaveBeenCalledWith('abc123def456', 'hello'));
  });

  it('keeps Shift+Enter as a new line and does not send', async () => {
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.change(composer(), { target: { value: 'first line' } });
    fireEvent.keyDown(composer(), { key: 'Enter', shiftKey: true });

    expect(api.createConversation).not.toHaveBeenCalled();
    expect(api.sendMessage).not.toHaveBeenCalled();
  });

  it('shows the thinking note while the model answers, then the reply and the draft note', async () => {
    let answer: (value: unknown) => void = () => {};
    api.sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    api.getConversation.mockResolvedValue({
      ...conversation,
      messages: [
        { role: 'user', content: 'plan it', at: '' },
        { role: 'assistant', content: 'done', drafts: ['ug-002.md'], at: '' },
      ],
    });
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.change(composer(), { target: { value: 'plan it' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Orchestrator is replying');
    expect(document.querySelectorAll('.lys-wave-dot')).toHaveLength(3);
    answer({ role: 'assistant', content: 'done', drafts: ['ug-002.md'], at: '' });

    expect(await screen.findByText(/Draft saved: ug-002\.md/)).toBeInTheDocument();
    expect(screen.getByText(/Only you can mark a brief Ready/)).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows a failed send inline and keeps the human message in the transcript', async () => {
    api.createConversation.mockResolvedValue(conversation);
    api.sendMessage.mockRejectedValue(new Error('model call failed'));
    api.getConversation.mockResolvedValue({ ...conversation, messages: [{ role: 'user', content: 'still there?', at: '' }] });
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.change(composer(), { target: { value: 'still there?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('model call failed');
    expect(screen.getByText('still there?')).toBeInTheDocument();
  });

  it('shows the API error when a chat cannot be created on the first message', async () => {
    api.createConversation.mockRejectedValue(new Error('model must be one of claude-sonnet-5-5, claude-opus-5-5'));
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.change(composer(), { target: { value: 'hello' } });
    fireEvent.keyDown(composer(), { key: 'Enter' });

    expect(await screen.findByRole('alert')).toHaveTextContent('model must be one of claude-sonnet-5-5, claude-opus-5-5');
  });
});
