import { describe, it, expect, vi } from 'vitest';
import { MockHermesApi } from '../api/adapters/mockAdapter';
import { resolveActorPresentation } from '../api/actors';

describe('MockHermesApi Contract Implementation', () => {
  const api = new MockHermesApi();

  it('should return a list of registered agents with character card metadata', async () => {
    const agents = await api.getAgents();
    expect(Array.isArray(agents)).toBe(true);
    expect(agents.length).toBeGreaterThan(0);
    
    const gemini = agents.find(a => a.id === 'gemini');
    expect(gemini).toBeDefined();
    expect(gemini?.displayName).toBe('Gemini');
    expect(gemini?.presentation?.characterCardUrl).toBeDefined();
    expect(gemini?.presentation?.accentColor).toBe('var(--lys-agent-gemini)');
  });

  it('should return detail for an existing agent', async () => {
    const agent = await api.getAgent('claude');
    expect(agent).not.toBeNull();
    expect(agent?.id).toBe('claude');
    expect(agent?.role).toContain('Architecture');
    expect(agent?.presentation?.characterCardUrl).toBe('/portrait/claude.png');
    expect(agent?.allowance.length).toBeGreaterThan(0);
  });

  it('should dynamically generate valid fallback detail for an unknown agent ID (e.g. Kimi)', async () => {
    const kimi = await api.getAgent('kimi');
    expect(kimi).not.toBeNull();
    expect(kimi?.id).toBe('kimi');
    expect(kimi?.displayName).toBe('Kimi');
    expect(kimi?.status).toBe('IDLE');
    expect(kimi?.capabilities.length).toBeGreaterThan(0);
  });

  it('should resolve agent and system presentation from actor resolver', async () => {
    const agents = await api.getAgents();
    
    const geminiActor = resolveActorPresentation('gemini', agents);
    expect(geminiActor.displayName).toBe('Gemini');
    expect(geminiActor.accentColor).toBe('var(--lys-agent-gemini)');

    const hermesActor = resolveActorPresentation('hermes', agents);
    expect(hermesActor.displayName).toBe('Hermes');
    expect(hermesActor.kind).toBe('runtime');

    const unknownActor = resolveActorPresentation('reviewer-8f92', agents);
    expect(unknownActor.displayName).toBe('Reviewer-8f92');
    expect(unknownActor.accentColor).toBe('var(--lys-text-muted)');
  });

  it('should return job queue and active job detail with normalized status', async () => {
    const jobs = await api.getJobs();
    expect(jobs.length).toBeGreaterThan(0);
    expect(jobs.some(j => j.status === 'COMPLETED')).toBe(true);

    const activeJob = await api.getJob('#142');
    expect(activeJob).not.toBeNull();
    expect(activeJob?.assignedAgentIds).toContain('gemini');
    expect(activeJob?.changedFiles?.length).toBeGreaterThan(0);
  });

  it('should support event subscriptions via subscribeEvents', () => {
    vi.useFakeTimers();
    const handler = vi.fn();
    const sub = api.subscribeEvents(handler);

    expect(handler).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2500);
    expect(handler).toHaveBeenCalled();

    sub.unsubscribe();
    const callCount = handler.mock.calls.length;
    vi.advanceTimersByTime(3000);
    expect(handler.mock.calls.length).toBe(callCount);

    vi.useRealTimers();
  });
});
