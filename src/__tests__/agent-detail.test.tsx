import { describe, it, expect } from 'vitest';
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
    expect(screen.getByText(/Dynamic Provider/i)).toBeInTheDocument();
  });
});
