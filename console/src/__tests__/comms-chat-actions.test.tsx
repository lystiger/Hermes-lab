import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  options: vi.fn(),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  createConversation: vi.fn(),
  sendMessage: vi.fn(),
  updateConversation: vi.fn(),
  deleteConversation: vi.fn(),
}));

vi.mock('../api/orchestrator', () => ({ orchestratorApi: api }));

import { CommsRoute } from '../routes/comms';

const summary = {
  id: 'abc123def456',
  title: 'Old chat',
  model: 'claude-sonnet-5-5',
  effort: null,
  system_commit: '0123456789abcdef',
  created: '2026-10-21T10:00:00+0700',
};
const chat = {
  ...summary,
  messages: [
    { role: 'user', content: 'plan it', at: '' },
    { role: 'assistant', content: 'here is the plan', drafts: [], at: '' },
  ],
};

beforeEach(() => {
  api.options.mockResolvedValue({
    providers: [{ id: 'claude', models: ['claude-sonnet-5-5', 'claude-opus-5-5'], efforts: ['low', 'high'] }],
  });
  api.listConversations.mockResolvedValue([summary]);
  api.getConversation.mockResolvedValue(chat);
  api.updateConversation.mockResolvedValue({ ...summary });
  api.deleteConversation.mockResolvedValue(undefined);
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

async function openOldChat() {
  renderRoute();
  fireEvent.click(await screen.findByRole('button', { name: 'Old chat' }));
  await screen.findByText('here is the plan');
}

describe('Comms chat actions', () => {
  it('renames a chat in place with Enter', async () => {
    await openOldChat();

    fireEvent.click(screen.getByRole('button', { name: 'Rename Old chat' }));
    const input = screen.getByLabelText('Chat title');
    fireEvent.change(input, { target: { value: 'Inquiry plan' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(api.updateConversation).toHaveBeenCalledWith('abc123def456', { title: 'Inquiry plan' }));
  });

  it('cancels a rename with Escape without saving', async () => {
    await openOldChat();

    fireEvent.click(screen.getByRole('button', { name: 'Rename Old chat' }));
    fireEvent.keyDown(screen.getByLabelText('Chat title'), { key: 'Escape' });

    expect(api.updateConversation).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Old chat' })).toBeInTheDocument();
  });

  it('deletes a chat only after the second click, and removes it from the list', async () => {
    await openOldChat();

    fireEvent.click(screen.getByRole('button', { name: 'Delete Old chat' }));
    expect(api.deleteConversation).not.toHaveBeenCalled();
    api.listConversations.mockResolvedValue([]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(api.deleteConversation).toHaveBeenCalledWith('abc123def456'));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Old chat' })).toBeNull());
  });

  it('keeps the chat when the delete is cancelled', async () => {
    await openOldChat();

    fireEvent.click(screen.getByRole('button', { name: 'Delete Old chat' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(api.deleteConversation).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Old chat' })).toBeInTheDocument();
  });

  it('copies a reply to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await openOldChat();

    fireEvent.click(screen.getByRole('button', { name: 'Copy reply' }));

    expect(writeText).toHaveBeenCalledWith('here is the plan');
  });

  it('changes the model of the open chat', async () => {
    await openOldChat();

    const header = screen.getByRole('combobox', { name: 'Model' });
    fireEvent.change(header, { target: { value: 'claude-opus-5-5' } });

    await waitFor(() => expect(api.updateConversation).toHaveBeenCalledWith('abc123def456', { model: 'claude-opus-5-5' }));
    expect(within(screen.getByRole('log', { name: 'Messages' })).getByText('plan it')).toBeInTheDocument();
  });
});
