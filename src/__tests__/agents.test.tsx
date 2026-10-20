import { describe, it, expect, vi } from 'vitest';
// These tests exercise the mock fixtures, which are opt-in only (VITE_LYSCONTROL_MOCK=1).
vi.hoisted(() => {
  process.env.VITE_LYSCONTROL_MOCK = '1';
});
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AgentPortrait } from '../features/agents/AgentPortrait';
import { AgentLaneCard } from '../features/agents/AgentLaneCard';
import { AgentDetailRoute } from '../routes/agents/$agentId';
import { AgentSummary } from '../api/types';

describe('Agent UI & Portrait Fallbacks', () => {
  it('renders generic agent without portrait cleanly using fallback sigil and initials', () => {
    const dynamicAgent: AgentSummary = {
      id: 'kimi',
      displayName: 'Kimi',
      provider: 'Moonshot AI',
      model: 'kimi-k3',
      role: 'Deep Research · Long-context',
      capabilities: ['research', 'long-context'],
      status: 'IDLE',
      phase: 'REVIEW',
      presentation: {
        displayName: 'Kimi',
        accentColor: '#8C949F',
        sigil: 'KIMI',
        code: 'KIMI'
      }
    };

    render(
      <MemoryRouter>
        <AgentLaneCard agent={dynamicAgent} size="compact" />
      </MemoryRouter>
    );

    // Checks name and model
    expect(screen.getByText('Kimi')).toBeInTheDocument();
    expect(screen.getByText('kimi-k3')).toBeInTheDocument();
    // Checks initials in fallback portrait (central sigil and bottom strip)
    expect(screen.getAllByText('K').length).toBeGreaterThanOrEqual(1);
  });

  it('renders portrayed agent correctly with portrait container', () => {
    render(
      <AgentPortrait
        displayName="Gemini"
        presentation={{
          displayName: 'Gemini',
          avatarUrl: '/portrait/gemini.png',
          characterCardUrl: '/agents/gemini-card.webp',
          accentColor: '#5B8CFF',
          sigil: 'BUILD'
        }}
        status="RUNNING"
        phase="BUILD"
      />
    );

    expect(screen.getByAltText('Gemini Portrait')).toBeInTheDocument();
    expect(screen.getByText('BUILD')).toBeInTheDocument();
  });

  it('gracefully handles missing presentation object altogether', () => {
    render(
      <AgentPortrait
        displayName="Subagent-99"
        status="IDLE"
        phase="CUSTOM"
      />
    );

    expect(screen.getAllByText('S').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('CUSTOM')).toBeInTheDocument();
  });

  it('renders view character sheet trigger on Agent Detail when characterCardUrl is present', async () => {
    render(
      <MemoryRouter initialEntries={['/agents/claude']}>
        <Routes>
          <Route path="/agents/:agentId" element={<AgentDetailRoute />} />
        </Routes>
      </MemoryRouter>
    );

    // The name appears in the roster and as the dossier heading; the heading is the dossier.
    expect(await screen.findByRole('heading', { name: 'Claude' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /character sheet/i })).toBeInTheDocument();
  });

  it('renders Agent Detail without view character sheet when characterCardUrl is not present', async () => {
    render(
      <MemoryRouter initialEntries={['/agents/unknown-subagent']}>
        <Routes>
          <Route path="/agents/:agentId" element={<AgentDetailRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Unknown-subagent')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /character sheet/i })).not.toBeInTheDocument();
  });
});
