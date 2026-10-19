import { describe, it, expect, vi } from 'vitest';

vi.hoisted(() => {
  process.env.VITE_LYSCONTROL_MOCK = '1';
});

import { render, screen } from '@testing-library/react';
import { AgentModelSelector } from '../features/agents/AgentModelSelector';
import { isMockMode } from '../api/client';

describe('AgentModelSelector in Mock Mode', () => {
  it('disables the control in mock mode with a tooltip explaining why', async () => {
    expect(isMockMode).toBe(true);

    render(<AgentModelSelector agentId="codex" />);

    // Model and Effort selects are disabled with tooltip
    const modelSelect = await screen.findByRole('combobox', { name: 'Model' });
    expect(modelSelect).toBeDisabled();
    expect(modelSelect).toHaveAttribute('title', 'Model configuration is disabled in mock mode');

    const effortSelect = screen.getByRole('combobox', { name: 'Effort' });
    expect(effortSelect).toBeDisabled();
    expect(effortSelect).toHaveAttribute('title', 'Model configuration is disabled in mock mode');

    // Save button is disabled with tooltip
    const saveButton = screen.getByRole('button', { name: 'Save' });
    expect(saveButton).toBeDisabled();
    expect(saveButton).toHaveAttribute('title', 'Model configuration is disabled in mock mode');
  });
});
