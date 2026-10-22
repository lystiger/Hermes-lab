import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentPortrait } from '../features/agents/AgentPortrait';
import { AgentDossier } from '../features/agents/AgentDossier';
import { AgentDetail } from '../api/types';

vi.mock('../features/agents/AgentModelSelector', () => ({ AgentModelSelector: () => <div>model panel</div> }));
vi.mock('../features/agents/AgentContextMeter', () => ({ AgentContextMeter: () => null }));

describe('agents are shown without character art', () => {
  it('shows the plain initials mark instead of a portrait', () => {
    render(
      <AgentPortrait
        displayName="Claude"
        presentation={{ code: 'CLD', accentColor: '#CBA35C', avatarUrl: '/portrait/claude.png' } as never}
        status="IDLE"
      />,
    );

    expect(screen.queryByRole('img', { name: /Portrait/ })).toBeNull();
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);
  });

  it('shows the initial mark in the dossier rather than a figure', () => {
    const agent = {
      id: 'claude',
      displayName: 'Claude',
      status: 'IDLE',
      provider: 'Anthropic API',
      model: 'claude-sonnet-4-5',
      role: 'architecture',
      capabilities: ['review'],
      presentation: {},
    } as unknown as AgentDetail;

    render(<AgentDossier agent={agent} />);

    expect(screen.queryByRole('img', { name: /character art/ })).toBeNull();
    expect(screen.queryAllByRole('img')).toHaveLength(0);
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);
  });
});
