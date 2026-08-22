import { describe, it, expect } from 'vitest';
import { MockLysStackApi } from '../api/adapters/mockAdapter';

describe('MockLysStackApi Contract Implementation', () => {
  const api = new MockLysStackApi();

  it('should return a list of registered agents', async () => {
    const agents = await api.getAgents();
    expect(Array.isArray(agents)).toBe(true);
    expect(agents.length).toBeGreaterThan(0);
    
    const gemini = agents.find(a => a.id === 'gemini');
    expect(gemini).toBeDefined();
    expect(gemini?.displayName).toBe('Gemini');
    expect(gemini?.capabilities).toContain('build');
  });

  it('should return detail for an existing agent', async () => {
    const agent = await api.getAgent('claude');
    expect(agent).not.toBeNull();
    expect(agent?.id).toBe('claude');
    expect(agent?.role).toContain('Architecture');
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

  it('should return job queue and active job detail', async () => {
    const jobs = await api.getJobs();
    expect(jobs.length).toBeGreaterThan(0);

    const activeJob = await api.getJob('#142');
    expect(activeJob).not.toBeNull();
    expect(activeJob?.assignedAgentIds).toContain('gemini');
    expect(activeJob?.changedFiles.length).toBeGreaterThan(0);
  });

  it('should return telemetry and provider quotas', async () => {
    const telemetry = await api.getTelemetry();
    expect(telemetry.tokensToday).toBeDefined();

    const quotas = await api.getProviderQuotas();
    expect(quotas.length).toBeGreaterThan(0);
  });
});
