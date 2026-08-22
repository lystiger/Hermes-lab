import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HttpLysStackApi } from '../api/adapters/httpAdapter';

describe('HttpLysStackApi Contract Implementation', () => {
  const baseUrl = 'http://localhost:8000';
  let api: HttpLysStackApi;

  beforeEach(() => {
    api = new HttpLysStackApi(baseUrl);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches and maps /health status successfully', async () => {
    const mockHealth = {
      status: 'ok',
      service: 'lysstack',
      version: '0.1.0',
      uptimeSeconds: 1842,
      timestamp: '2026-08-22T08:00:00Z'
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth
    } as any);

    const health = await api.getHealth();
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/health');
    expect(health.status).toBe('ok');
    expect(health.service).toBe('lysstack');
    expect(health.uptimeSeconds).toBe(1842);
  });

  it('throws an informative error if /health returns non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable'
    } as any);

    await expect(api.getHealth()).rejects.toThrow('HTTP 503: Service Unavailable');
  });

  it('fetches dynamic agent list and enhances presentation cleanly', async () => {
    const mockBackendAgents = [
      {
        id: 'gemini',
        displayName: 'Gemini',
        provider: 'Google AI Studio',
        model: 'antigravity-2.5-pro',
        role: 'Implementation',
        capabilities: ['build', 'refactoring'],
        status: 'RUNNING'
      },
      {
        id: 'custom-subagent',
        displayName: 'Custom Subagent',
        provider: 'Local',
        model: 'local-v1',
        role: 'Arbitrary Task Execution',
        capabilities: ['testing'],
        status: 'IDLE'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBackendAgents
    } as any);

    const agents = await api.getAgents();
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/agents');
    expect(agents.length).toBe(2);

    const gemini = agents.find((a) => a.id === 'gemini');
    expect(gemini?.displayName).toBe('Gemini');
    expect(gemini?.status).toBe('RUNNING');
    expect(gemini?.presentation?.characterCardUrl).toBe('/agents/gemini-card.webp');

    const custom = agents.find((a) => a.id === 'custom-subagent');
    expect(custom?.displayName).toBe('Custom Subagent');
    expect(custom?.status).toBe('IDLE');
    expect(custom?.presentation?.accentColor).toBeDefined();
  });

  it('returns truthful unobserved telemetry for getAgent in real mode (no fabricated stats)', async () => {
    const mockBackendAgents = [
      {
        id: 'claude',
        displayName: 'Claude',
        provider: 'Anthropic API',
        model: 'claude-sonnet-4-5',
        role: 'Architecture',
        capabilities: ['security-review'],
        status: 'IDLE'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBackendAgents
    } as any);

    const detail = await api.getAgent('claude');
    expect(detail).not.toBeNull();
    expect(detail?.id).toBe('claude');
    // Verify no fabricated token numbers
    expect(detail?.input).toBe('—');
    expect(detail?.output).toBe('—');
    expect(detail?.activity).toEqual([]);
    expect(detail?.runs).toEqual([]);
  });

  it('truthfully reports that commands and job actions are unsupported in real mode', async () => {
    const cmdResult = await api.sendOperatorCommand('claude', 'run lint');
    expect(cmdResult.success).toBe(false);
    expect(cmdResult.response).toContain('not available in real control-plane mode yet');

    const actionResult = await api.triggerJobAction('#142', 'retry');
    expect(actionResult).toBe(false);
  });

  it('fetches events with limit and cursor', async () => {
    const mockEvents = [
      {
        id: 'evt_100',
        ts: '10:42:01.123',
        rawTs: 1771663321,
        source: {
          id: 'claude',
          kind: 'agent',
          displayName: 'Claude',
          accentColor: '#D9A05B'
        },
        kind: 'agent.finished',
        detail: 'Harden phase complete',
        dur: '2.1s'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockEvents
    } as any);

    const events = await api.getTraceEvents(50, 'evt_099');
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/events?limit=50&after=evt_099');
    expect(events.length).toBe(1);
    expect(events[0].id).toBe('evt_100');
    expect(events[0].source.displayName).toBe('Claude');
  });

  it('handles SSE streaming subscription with cursor and clean unsubscription', () => {
    let messageListener: any = null;
    let closed = false;
    let openedUrl = '';

    // Mock EventSource
    class MockEventSource {
      constructor(public url: string) {
        openedUrl = url;
      }
      addEventListener(type: string, listener: any) {
        if (type === 'trace') {
          messageListener = listener;
        }
      }
      removeEventListener() {}
      close() {
        closed = true;
      }
    }

    (global as any).EventSource = MockEventSource;

    const handler = vi.fn();
    const sub = api.subscribeEvents(handler, undefined, 'evt_050');

    expect(openedUrl).toBe('http://localhost:8000/events/stream?after=evt_050');
    expect(messageListener).toBeDefined();

    // Dispatch simulated message event
    const sampleEventDTO = {
      id: 'evt_200',
      ts: '10:45:00.000',
      rawTs: 1771663500,
      source: {
        id: 'gemini',
        kind: 'agent',
        displayName: 'Gemini'
      },
      kind: 'agent.started',
      detail: 'Starting sprint build phase'
    };

    messageListener({ data: JSON.stringify(sampleEventDTO) });

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'evt_200',
        kind: 'agent.started',
        detail: 'Starting sprint build phase'
      })
    );

    sub.unsubscribe();
    expect(closed).toBe(true);
  });
});
