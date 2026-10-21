import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const hooks = vi.hoisted(() => ({
  useAgents: vi.fn(),
  useAgentModels: vi.fn(),
}));

vi.mock('../api/hooks', () => hooks);

import { AgentsListRoute } from '../routes/agents/index';

const agents = [
  { id: 'claude', displayName: 'Claude', provider: 'Anthropic', model: 'sonnet', role: 'architect', capabilities: [], status: 'IDLE' },
  { id: 'codex', displayName: 'Codex', provider: 'OpenAI', model: 'gpt-5', role: 'verifier', capabilities: [], status: 'IDLE' },
];

function mockData({ modelsMap = {}, agentList = agents }: { modelsMap?: Record<string, unknown>; agentList?: unknown[] } = {}) {
  hooks.useAgents.mockReturnValue({ agents: agentList, loading: false, error: null, refetch: vi.fn(), updatedAt: null, stale: false });
  hooks.useAgentModels.mockReturnValue({ models: modelsMap, loading: false, error: null, refetch: vi.fn(), updatedAt: null, stale: false });
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
  it('lists each agent with its provider, configured model and reasoning effort', () => {
    mockData({
      modelsMap: {
        claude: { configured: { default: 'opus', effort: 'high' }, allowed: ['sonnet', 'opus'], lastUsed: null },
        codex: { configured: { default: null, effort: null }, allowed: [], lastUsed: { model: 'gpt-5-codex', effort: 'medium', source: 'phase' } },
      },
    });

    renderPage();

    const rows = screen.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Claude')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Anthropic')).toBeInTheDocument();
    expect(within(rows[0]).getByText('opus')).toBeInTheDocument();
    expect(within(rows[0]).getByText('high')).toBeInTheDocument();
    expect(within(rows[1]).getByText('gpt-5-codex')).toBeInTheDocument();
    expect(within(rows[1]).getByText('medium')).toBeInTheDocument();
  });

  it('shows a dash when the model or effort is not known', () => {
    mockData({ modelsMap: {} });

    renderPage();

    const row = screen.getAllByRole('row')[1];
    expect(within(row).getAllByText('—')).toHaveLength(2);
  });

  it('has no images, portraits or art frames', () => {
    mockData({ modelsMap: {} });

    const { container } = renderPage();

    expect(container.querySelectorAll('img')).toHaveLength(0);
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('says there are no agents when the list is empty', () => {
    mockData({ agentList: [], modelsMap: {} });

    renderPage();

    expect(screen.getByText('No agents')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
