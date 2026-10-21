import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const hooks = vi.hoisted(() => ({
  useAgents: vi.fn(),
  useAgentModels: vi.fn(),
}));
const api = vi.hoisted(() => ({ setAgentModel: vi.fn() }));

vi.mock('../api/hooks', () => hooks);
vi.mock('../api/client', () => ({ hermesApi: api, isMockMode: false }));

import { AgentsListRoute } from '../routes/agents/index';

const agents = [
  { id: 'claude', displayName: 'Claude', provider: 'Anthropic', model: 'claude-sonnet-5-5', role: 'architect', capabilities: [], status: 'IDLE' },
  { id: 'codex', displayName: 'Codex', provider: 'OpenAI', model: 'gpt-5', role: 'verifier', capabilities: [], status: 'IDLE' },
];

const models = {
  claude: { configured: { default: 'claude-opus-5-5', effort: null }, allowed: ['claude-sonnet-5-5', 'claude-opus-5-5'], lastUsed: null },
  codex: { configured: { default: null, effort: null }, allowed: ['gpt-5-codex', 'gpt-5.4'], lastUsed: { model: 'gpt-5-codex', effort: 'medium', source: 'phase' } },
};

function mockData({ modelsMap = models, agentList = agents }: { modelsMap?: Record<string, unknown>; agentList?: unknown[] } = {}) {
  const refetchModels = vi.fn();
  hooks.useAgents.mockReturnValue({ agents: agentList, loading: false, error: null, refetch: vi.fn(), updatedAt: null, stale: false });
  hooks.useAgentModels.mockReturnValue({ models: modelsMap, loading: false, error: null, refetch: refetchModels, updatedAt: null, stale: false });
  return { refetchModels };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AgentsListRoute />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Agents list page', () => {
  it('lists each agent with its provider and a model picker with the configured value', () => {
    mockData();

    renderPage();

    const rows = screen.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Claude')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Anthropic')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Model for Claude' })).toHaveValue('claude-opus-5-5');
    expect(screen.getByRole('combobox', { name: 'Model for Codex' })).toHaveValue('gpt-5-codex');
  });

  it('offers only the models the registry allows, and the reasoning options for the agent', () => {
    mockData();

    renderPage();

    const claudeModel = screen.getByRole('combobox', { name: 'Model for Claude' }) as HTMLSelectElement;
    expect([...claudeModel.options].map((o) => o.value)).toEqual(['claude-sonnet-5-5', 'claude-opus-5-5']);
    const codexReasoning = screen.getByRole('combobox', { name: 'Reasoning for Codex' }) as HTMLSelectElement;
    expect(codexReasoning.options.length).toBeGreaterThan(2);
    const claudeReasoning = screen.getByRole('combobox', { name: 'Reasoning for Claude' }) as HTMLSelectElement;
    expect(claudeReasoning).toBeDisabled();
  });

  it('keeps Save off until something is changed, then saves the pick and refreshes', async () => {
    const { refetchModels } = mockData();
    api.setAgentModel.mockResolvedValue({ default: 'claude-sonnet-5-5', effort: null });
    renderPage();

    const row = screen.getAllByRole('row')[1];
    const save = within(row).getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByRole('combobox', { name: 'Model for Claude' }), { target: { value: 'claude-sonnet-5-5' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(api.setAgentModel).toHaveBeenCalledWith('claude', 'claude-sonnet-5-5', null));
    await waitFor(() => expect(refetchModels).toHaveBeenCalled());
  });

  it('shows the save error on the row instead of failing silently', async () => {
    mockData();
    api.setAgentModel.mockRejectedValue(new Error('model not allowed'));
    renderPage();

    fireEvent.change(screen.getByRole('combobox', { name: 'Model for Claude' }), { target: { value: 'claude-sonnet-5-5' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[0]);

    expect(await screen.findByRole('alert')).toHaveTextContent('model not allowed');
  });

  it('has no images, portraits or art frames', () => {
    mockData();

    const { container } = renderPage();

    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('says there are no agents when the list is empty', () => {
    mockData({ agentList: [], modelsMap: {} });

    renderPage();

    expect(screen.getByText('No agents')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
