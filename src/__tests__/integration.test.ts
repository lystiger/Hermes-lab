import { describe, it, expect } from 'vitest';
import { useConsoleStore } from '../stores/useConsoleStore';
import { HttpLysStackApi } from '../api/adapters/httpAdapter';
import { TraceEvent } from '../api/types';

describe('End-to-End Real Event Pipeline Flow', () => {
  it('propagates a real runtime event from SSE adapter -> Zustand store -> state update', () => {
    let sseCallback: any = null;

    class MockEventSource {
      constructor(public url: string) {}
      addEventListener(type: string, listener: any) {
        if (type === 'trace') {
          sseCallback = listener;
        }
      }
      removeEventListener() {}
      close() {}
    }

    (global as any).EventSource = MockEventSource;

    const api = new HttpLysStackApi('http://localhost:8000');

    // Subscribe store to API adapter
    const sub = api.subscribeEvents((evt: TraceEvent) => {
      useConsoleStore.getState().addTraceEvent(evt);
    });

    expect(sseCallback).toBeDefined();

    // Simulate real event arriving from Hermes Runtime API
    const incomingRealEvent = {
      id: 'evt_real_001',
      ts: '10:48:12.456',
      rawTs: 1771663692,
      source: {
        id: 'claude',
        kind: 'agent',
        displayName: 'Claude',
        accentColor: '#D9A05B'
      },
      kind: 'agent.finished',
      detail: 'Phase HARDEN completed successfully in worktree sprint-02',
      dur: '3.42s'
    };

    sseCallback({ data: JSON.stringify(incomingRealEvent) });

    const updatedEvents = useConsoleStore.getState().allEvents;
    expect(updatedEvents.length).toBeGreaterThan(0);
    expect(updatedEvents[0].id).toBe('evt_real_001');
    expect(updatedEvents[0].source.displayName).toBe('Claude');
    expect(updatedEvents[0].detail).toContain('Phase HARDEN completed successfully');

    sub.unsubscribe();
  });
});
