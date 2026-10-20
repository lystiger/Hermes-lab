import { describe, it, expect, vi } from 'vitest';
// These tests exercise the mock fixtures, which are opt-in only (VITE_LYSCONTROL_MOCK=1).
vi.hoisted(() => {
  process.env.VITE_LYSCONTROL_MOCK = '1';
});
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AgentDetailRoute } from '../routes/agents/$agentId';

describe('Agent Detail Route with Dynamic & Unknown Agents', () => {
  it('renders dynamic agent details without throwing or requiring static map entries', async () => {
    render(
      <MemoryRouter initialEntries={['/agents/kimi']}>
        <Routes>
          <Route path="/agents/:agentId" element={<AgentDetailRoute />} />
        </Routes>
      </MemoryRouter>
    );

    // Kimi should dynamically load and render via mock adapter fallback
    expect(await screen.findByText('Kimi')).toBeInTheDocument();
    // The provider appears in the roster presence card and the dossier.
    expect(screen.getAllByText(/Dynamic Provider/i).length).toBeGreaterThan(0);
  });
});
