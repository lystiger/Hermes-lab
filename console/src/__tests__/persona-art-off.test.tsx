import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentPortrait } from '../features/agents/AgentPortrait';
import { AgentDossier } from '../features/agents/AgentDossier';
import { AgentDetail } from '../api/types';
import { agentArt, DESIGN_ART_ENABLED, HERMES_ART, PERSONA_ART_ENABLED } from '../theme/agentArt';

vi.mock('../features/agents/AgentModelSelector', () => ({ AgentModelSelector: () => <div>model panel</div> }));
vi.mock('../features/agents/AgentContextMeter', () => ({ AgentContextMeter: () => null }));

describe('persona and design art are off on this branch', () => {
  it('turns the anime portraits and decorative art off', () => {
    expect(PERSONA_ART_ENABLED).toBe(false);
    expect(DESIGN_ART_ENABLED).toBe(false);
  });

  it('gives no character art and no emblem', () => {
    expect(agentArt('claude')).toBeUndefined();
    expect(agentArt('codex')).toBeUndefined();
    expect(HERMES_ART).toBeUndefined();
  });

  it('shows the plain initials mark instead of a portrait', () => {
    render(
      <AgentPortrait
        displayName="Claude"
        presentation={{ code: 'CLD', accentColor: '#CBA35C', avatarUrl: '/portrait/claude.png' } as never}
        status="IDLE"
        phase="IDLE"
      />,
    );

    expect(screen.queryByRole('img', { name: /Portrait/ })).toBeNull();
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);
  });

  it('says there is no art in the dossier rather than showing a figure', () => {
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
    expect(screen.getByText('No art')).toBeInTheDocument();
  });
});
