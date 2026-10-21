import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AgentModelSelector, getValidEffortOptions } from '../features/agents/AgentModelSelector';
import { hermesApi } from '../api/client';
import { AgentModelsMap } from '../api/types';

describe('AgentModelSelector Component', () => {
  const sampleModels: AgentModelsMap = {
    codex: {
      configured: { default: 'gpt-6.1-sol', effort: 'low' },
      allowed: ['gpt-5-codex', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-6.1-sol'],
      lastUsed: { model: 'sonnet', effort: null, source: 'phase' }
    },
    claude: {
      configured: null,
      allowed: ['claude-3-7-sonnet', 'claude-3-5-sonnet'],
      lastUsed: null
    },
    gemini: {
      configured: { default: 'gemini-2.5-pro', effort: 'high' },
      allowed: ['gemini-2.5-pro', 'gemini-2.5-flash'],
      lastUsed: { model: 'gemini-2.5-pro', effort: 'high', source: 'phase' }
    }
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders configured and last used distinctly', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);

    render(<AgentModelSelector agentId="codex" />);

    expect(await screen.findByText('Model configuration')).toBeInTheDocument();

    // Check Configured block
    const configuredBlock = screen.getByLabelText('Configured model');
    expect(within(configuredBlock).getByText('Configured')).toBeInTheDocument();
    expect(within(configuredBlock).getByText('gpt-6.1-sol')).toBeInTheDocument();
    expect(within(configuredBlock).getByText('low')).toBeInTheDocument();

    // Check Last used block
    const lastUsedBlock = screen.getByLabelText('Last used model');
    expect(within(lastUsedBlock).getByText('Last used')).toBeInTheDocument();
    expect(within(lastUsedBlock).getByText('sonnet')).toBeInTheDocument();
    expect(within(lastUsedBlock).getByText('phase')).toBeInTheDocument();

    // Notice text
    expect(screen.getByText('Applies to the next phase')).toBeInTheDocument();
  });

  it('shows — and "CLI default" when nothing is configured', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);

    render(<AgentModelSelector agentId="claude" />);

    expect(await screen.findByText('Model configuration')).toBeInTheDocument();

    // In Claude's config, configured is null:
    expect(screen.getByText('CLI default')).toBeInTheDocument();
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it('populates model options only from the allowed list', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);

    render(<AgentModelSelector agentId="codex" />);

    const modelSelect = (await screen.findByRole('combobox', { name: 'Model' })) as HTMLSelectElement;
    const optionValues = Array.from(modelSelect.options).map((o) => o.value).filter(Boolean);

    expect(optionValues).toEqual(sampleModels.codex.allowed);
  });

  it('effort options depend on the agent identity', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);

    // Codex options: null, minimal, low, medium, high, xhigh
    const { unmount } = render(<AgentModelSelector agentId="codex" />);
    const codexEffortSelect = (await screen.findByRole('combobox', { name: 'Effort' })) as HTMLSelectElement;
    const codexOptions = Array.from(codexEffortSelect.options).map((o) => o.value);
    expect(codexOptions).toEqual(['', 'minimal', 'low', 'medium', 'high', 'xhigh']);
    unmount();

    // Gemini options: null, low, medium, high
    render(<AgentModelSelector agentId="gemini" />);
    const geminiEffortSelect = (await screen.findByRole('combobox', { name: 'Effort' })) as HTMLSelectElement;
    const geminiOptions = Array.from(geminiEffortSelect.options).map((o) => o.value);
    expect(geminiOptions).toEqual(['', 'low', 'medium', 'high']);
    expect(geminiOptions).not.toContain('minimal');
    expect(geminiOptions).not.toContain('xhigh');

    // Claude options: null, then the Claude CLI levels
    expect(getValidEffortOptions('claude')).toEqual([null, 'low', 'medium', 'high', 'xhigh', 'max']);
  });

  it('keeps Save button disabled until changed and valid', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);

    render(<AgentModelSelector agentId="codex" />);

    const saveButton = await screen.findByRole('button', { name: 'Save' });
    expect(saveButton).toBeDisabled();

    // Change model to an allowed alternative
    const modelSelect = screen.getByRole('combobox', { name: 'Model' });
    fireEvent.change(modelSelect, { target: { value: 'gpt-5.4' } });

    // Now changed and valid -> Save is enabled
    expect(saveButton).toBeEnabled();

    // Reverting to baseline model disables Save again
    fireEvent.change(modelSelect, { target: { value: 'gpt-6.1-sol' } });
    expect(saveButton).toBeDisabled();

    // Changing effort enables Save
    const effortSelect = screen.getByRole('combobox', { name: 'Effort' });
    fireEvent.change(effortSelect, { target: { value: 'high' } });
    expect(saveButton).toBeEnabled();
  });

  it('on success refreshes from server and updates configured view', async () => {
    let currentModels = JSON.parse(JSON.stringify(sampleModels));
    const getSpy = vi.spyOn(hermesApi, 'getAgentModels').mockImplementation(async () => currentModels);
    const setSpy = vi.spyOn(hermesApi, 'setAgentModel').mockImplementation(async (_id, model, effort) => {
      currentModels = {
        ...currentModels,
        codex: {
          ...currentModels.codex,
          configured: { default: model, effort: effort ?? null }
        }
      };
      return { default: model, effort: effort ?? null };
    });

    render(<AgentModelSelector agentId="codex" />);

    const saveButton = await screen.findByRole('button', { name: 'Save' });
    const modelSelect = screen.getByRole('combobox', { name: 'Model' });

    fireEvent.change(modelSelect, { target: { value: 'gpt-5.4' } });
    expect(saveButton).toBeEnabled();

    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(setSpy).toHaveBeenCalledWith('codex', 'gpt-5.4', 'low');
      expect(getSpy).toHaveBeenCalledTimes(2);
    });

    // Save button disabled after successful update
    await waitFor(() => {
      expect(saveButton).toBeDisabled();
    });

    // Configured model display updated to gpt-5.4
    const configuredBlock = screen.getByLabelText('Configured model');
    expect(within(configuredBlock).getByText('gpt-5.4')).toBeInTheDocument();
  });

  it('on error keeps the user selection, prevents optimistic update, and displays server error message', async () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(sampleModels);
    vi.spyOn(hermesApi, 'setAgentModel').mockRejectedValue(
      new Error("Model 'gpt-5.4' is temporarily restricted by provider quota")
    );

    render(<AgentModelSelector agentId="codex" />);

    const saveButton = await screen.findByRole('button', { name: 'Save' });
    const modelSelect = screen.getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;

    // Change model to gpt-5.4
    fireEvent.change(modelSelect, { target: { value: 'gpt-5.4' } });
    expect(modelSelect.value).toBe('gpt-5.4');

    fireEvent.click(saveButton);

    // Error state appears with server error message
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Model 'gpt-5.4' is temporarily restricted by provider quota");

    // User selection is kept (not reverted)
    expect(modelSelect.value).toBe('gpt-5.4');

    // Configured view still shows original gpt-6.1-sol (no optimistic update)
    expect(screen.getByTitle('gpt-6.1-sol')).toBeInTheDocument();
  });

  it('renders loading state when initial fetch is pending', () => {
    vi.spyOn(hermesApi, 'getAgentModels').mockReturnValue(new Promise(() => {}));

    render(<AgentModelSelector agentId="codex" />);
    expect(screen.getByText('Agent models')).toBeInTheDocument();
  });

  it('renders error state with retry button when initial fetch fails', async () => {
    const errorSpy = vi.spyOn(hermesApi, 'getAgentModels').mockRejectedValue(new Error('Connection refused'));

    render(<AgentModelSelector agentId="codex" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Agent models failed');
    expect(screen.getByRole('button', { name: 'retry' })).toBeInTheDocument();

    // Clicking retry calls getAgentModels again
    errorSpy.mockResolvedValueOnce(sampleModels);
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    expect(await screen.findByText('Model configuration')).toBeInTheDocument();
  });

  it('renders empty state ("No models") when allowed list is empty or agent has no models', async () => {
    const emptyModels: AgentModelsMap = {
      codex: {
        configured: null,
        allowed: [],
        lastUsed: null
      }
    };
    vi.spyOn(hermesApi, 'getAgentModels').mockResolvedValue(emptyModels);

    render(<AgentModelSelector agentId="codex" />);

    expect(await screen.findByText('No models')).toBeInTheDocument();
  });
});
