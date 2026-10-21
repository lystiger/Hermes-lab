import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AgentDossier } from '../features/agents/AgentDossier';
import { AgentDetail } from '../api/types';
import { PERSONA_ART_ENABLED } from '../theme/agentArt';

vi.mock('../features/agents/AgentModelSelector', () => ({ AgentModelSelector: () => <div>model panel</div> }));
vi.mock('../features/agents/AgentContextMeter', () => ({ AgentContextMeter: () => null }));

const agent = {
  id: 'claude',
  displayName: 'Claude',
  status: 'IDLE',
  provider: 'Anthropic API',
  model: 'claude-sonnet-4-5',
  role: 'architecture',
  capabilities: ['review'],
  presentation: {}
} as unknown as AgentDetail;

describe('agent dossier details toggle', () => {
  // Anime persona art is off on this branch; this runs on style/anime-persona.
  it.skipIf(!PERSONA_ART_ENABLED)('hides the details column and gives the art the full width, then restores it', () => {
    render(<AgentDossier agent={agent} />);
    const toggle = screen.getByRole('button', { name: 'Hide details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAttribute('aria-controls', 'agent-details');
    expect(document.getElementById('agent-details')).not.toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: 'Show details' })).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('agent-details')).toBeNull();
    expect(screen.queryByText('model panel')).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Claude character art' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show details' }));
    expect(screen.getByText('model panel')).toBeInTheDocument();
  });
});
