import { describe, it, expect, vi, afterEach } from 'vitest';
import { HttpHermesApi } from '../api/adapters/httpAdapter';

/** Every request carries a timeout signal (see REQUEST_TIMEOUT_MS in httpAdapter). */
const TIMED = expect.objectContaining({ signal: expect.anything() });

describe('HttpHermesApi.getExecutionSnapshot (GET /execution)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps backends, resources and the openrig block from the contract shape', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        backends: [{ name: 'herdr', available: false, detail: 'socket down' }],
        resources: [
          {
            backend: 'openrig',
            kind: 'seat',
            id: 'seat-1',
            label: 'builder-1',
            state: 'idle',
            since: '2026-10-14T10:00:00Z',
            expiresAt: '2026-10-14T10:10:00Z',
            details: { reused: true }
          }
        ],
        openrig: { daemon: 'up', ledger: { owners: 2, rigIds: ['rig-a'] } }
      })
    } as any);

    const snapshot = await new HttpHermesApi('http://localhost:8000').getExecutionSnapshot();

    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/execution', TIMED);
    expect(snapshot.backends).toEqual([{ name: 'herdr', available: false, detail: 'socket down' }]);
    expect(snapshot.resources[0]).toMatchObject({ state: 'idle', jobId: null, taskId: null, executionId: null });
    expect(snapshot.openrig).toEqual({ daemon: 'up', ledger: { owners: 2, rigIds: ['rig-a'] } });
  });

  it('throws on a non-OK response so the page can show the failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: 'Not Found' } as any);
    await expect(new HttpHermesApi('http://localhost:8000').getExecutionSnapshot()).rejects.toThrow('HTTP 404');
  });
});
