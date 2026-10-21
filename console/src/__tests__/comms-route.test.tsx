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
  model: 'sonnet',
  effort: null,
  system_commit: '0123456789abcdef',
  created: '2026-10-21T10:00:00+0700',
  messages: [],
};

beforeEach(() => {
  api.options.mockResolvedValue({
    providers: [{ id: 'claude', models: ['sonnet', 'opus', 'haiku'], efforts: ['low', 'high'] }],
  });
  api.listConversations.mockResolvedValue([]);
  api.createConversation.mockResolvedValue(conversation);
  api.getConversation.mockResolvedValue(conversation);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderRoute() {
  return render(
    <MemoryRouter>
      <CommsRoute />
    </MemoryRouter>,
  );
}

describe('Comms route', () => {
  it('offers only the models and efforts the API reports, and says it has no tools', async () => {
    renderRoute();

    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Model' })).toBeInTheDocument());
    const model = screen.getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    expect([...model.options].map((o) => o.value)).toEqual(['sonnet', 'opus', 'haiku']);
    expect(screen.getByText(/chat only, no tools/i)).toBeInTheDocument();
  });

  it('starts a chat with the chosen model and an empty effort as the default', async () => {
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.change(screen.getByRole('combobox', { name: 'Model' }), { target: { value: 'opus' } });
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

    await waitFor(() => expect(api.createConversation).toHaveBeenCalledWith('opus', null));
  });

  it('shows the reply and tells the human where drafts were saved', async () => {
    api.createConversation.mockResolvedValue(conversation);
    api.sendMessage.mockResolvedValue({ role: 'assistant', content: 'done', drafts: ['ug-002.md'], at: '' });
    api.getConversation.mockResolvedValueOnce({
      ...conversation,
      messages: [
        { role: 'user', content: 'plan it', at: '' },
        { role: 'assistant', content: 'done', drafts: ['ug-002.md'], at: '' },
      ],
    });
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    await waitFor(() => expect(api.createConversation).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'plan it' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(api.sendMessage).toHaveBeenCalledWith('abc123def456', 'plan it'));
    expect(await screen.findByText(/Saved to LysStack\/drafts: ug-002\.md/)).toBeInTheDocument();
    expect(screen.getByText(/Only you can mark a brief Ready/)).toBeInTheDocument();
  });

  it('shows the API error instead of failing silently', async () => {
    api.createConversation.mockRejectedValue(new Error('model must be one of sonnet, opus, haiku'));
    renderRoute();
    await waitFor(() => expect(api.options).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('model must be one of sonnet, opus, haiku');
  });
});
