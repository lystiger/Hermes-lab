import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HttpHermesApi } from '../api/adapters/httpAdapter';
import { hermesApi } from '../api/client';
import { useEventStream } from '../api/hooks';
import { TraceEvent } from '../api/types';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';

vi.mock('../api/client', async () => {
  const { HttpHermesApi } = await import('../api/adapters/httpAdapter');
  return { hermesApi: new HttpHermesApi(), isRealApiMode: true, isMockMode: false };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const event = (id: string, rawTs: number) => ({ id, rawTs, kind: 'test' }) as TraceEvent;
const response = (data: unknown) => new Response(JSON.stringify(data));

describe('M9 stream startup idle barrier', () => {
  beforeEach(() => {
    useConsoleStore.setState({ allEvents: [] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({})));
    vi.spyOn(hermesApi, 'getTraceEvents').mockResolvedValue([
      event('middle', 20), event('newest', 30), event('oldest', 10)
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(['success', 'failure'] as const)('waits for every outstanding request, including %s, then uses the newest cursor', async (outcome) => {
    const first = deferred<Response>();
    const last = deferred<Response>();
    vi.mocked(fetch).mockImplementation((url) => {
      if (String(url).endsWith('/agents')) return first.promise;
      if (new URL(String(url)).pathname === '/jobs') return last.promise;
      return Promise.resolve(response({}));
    });
    const agents = hermesApi.getAgents();
    // Attach the failure handler before deliberately rejecting the fetch.
    const jobs = hermesApi.getJobs().catch(() => []);
    const subscribe = vi.spyOn(hermesApi, 'subscribeEvents').mockReturnValue({ unsubscribe: vi.fn() });
    const { unmount } = renderHook(() => useEventStream());
    await waitFor(() => expect(hermesApi.getTraceEvents).toHaveBeenCalled());
    expect(subscribe).not.toHaveBeenCalled();

    await act(async () => { first.resolve(response([])); await agents; });
    expect(subscribe).not.toHaveBeenCalled();
    await act(async () => {
      if (outcome === 'success') last.resolve(response([]));
      else last.reject(new Error('offline'));
      await jobs;
    });
    expect(subscribe).toHaveBeenCalledExactlyOnceWith(expect.any(Function), expect.any(Function), 'newest');
    unmount();
  });

  it('opens immediately when already idle and keeps drop/resync handling', async () => {
    const unsubscribe = vi.fn();
    const subscribe = vi.spyOn(hermesApi, 'subscribeEvents').mockReturnValue({ unsubscribe });
    const refresh = vi.spyOn(useExecutionStore.getState(), 'refreshSnapshot').mockResolvedValue();
    const resync = vi.spyOn(useConsoleStore.getState(), 'markRuntimeResynced');
    const { unmount } = renderHook(() => useEventStream());
    await waitFor(() => expect(subscribe).toHaveBeenCalledOnce());
    const [onEvent, onError] = subscribe.mock.calls[0];
    act(() => { onError?.(new Error('disconnected')); onEvent(event('gap-event', 40)); });
    expect(refresh).toHaveBeenCalledOnce();
    expect(resync).toHaveBeenCalledOnce();
    act(() => onEvent(event('next-event', 50)));
    expect(refresh).toHaveBeenCalledOnce();
    unmount();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it('does not open a stream if unmounted while waiting for idle', async () => {
    const pending = deferred<Response>();
    vi.mocked(fetch).mockReturnValueOnce(pending.promise);
    const agents = hermesApi.getAgents();
    const subscribe = vi.spyOn(hermesApi, 'subscribeEvents');
    const { unmount } = renderHook(() => useEventStream());
    await waitFor(() => expect(hermesApi.getTraceEvents).toHaveBeenCalled());
    unmount();
    await act(async () => { pending.resolve(response([])); await agents; });
    expect(subscribe).not.toHaveBeenCalled();
  });

  it('rechecks idle if another request starts before the waiter resumes', async () => {
    const api = new HttpHermesApi();
    const first = deferred<Response>();
    const second = deferred<Response>();
    vi.mocked(fetch).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const firstRequest = api.getHealth();
    let idle = false;
    const barrier = api.waitForIdle().then(() => { idle = true; });
    first.resolve(response({}));
    await Promise.resolve();
    const secondRequest = api.getHealth();
    await firstRequest;
    expect(idle).toBe(false);
    second.resolve(response({}));
    await Promise.all([secondRequest, barrier]);
    expect(idle).toBe(true);
  });

  it('reloads history after the wait when it had no cursor, so events from the wait are not lost', async () => {
    const pending = deferred<Response>();
    vi.mocked(fetch).mockReturnValueOnce(pending.promise);
    const agents = hermesApi.getAgents();
    vi.mocked(hermesApi.getTraceEvents).mockResolvedValueOnce([]).mockResolvedValueOnce([event('during-wait', 60)]);
    const subscribe = vi.spyOn(hermesApi, 'subscribeEvents').mockReturnValue({ unsubscribe: vi.fn() });
    const { unmount } = renderHook(() => useEventStream());
    await waitFor(() => expect(hermesApi.getTraceEvents).toHaveBeenCalledOnce());
    await act(async () => { pending.resolve(response([])); await agents; });
    await waitFor(() => expect(subscribe).toHaveBeenCalledOnce());
    expect(hermesApi.getTraceEvents).toHaveBeenCalledTimes(2);
    expect(subscribe).toHaveBeenCalledWith(expect.any(Function), expect.any(Function), 'during-wait');
    expect(useConsoleStore.getState().allEvents).toContainEqual(event('during-wait', 60));
    unmount();
  });
  it('waits until an outstanding response body has arrived, not only its headers', async () => {
    const body = deferred<Uint8Array>();
    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        controller.enqueue(await body.promise);
        controller.close();
      }
    });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(stream));
    let agentsSettled = false;
    const agents = hermesApi.getAgents().then(() => { agentsSettled = true; });
    const subscribe = vi.spyOn(hermesApi, 'subscribeEvents').mockReturnValue({ unsubscribe: vi.fn() });
    const { unmount } = renderHook(() => useEventStream());
    try {
      await waitFor(() => expect(hermesApi.getTraceEvents).toHaveBeenCalledOnce());
      await act(async () => { await Promise.resolve(); });
      expect(agentsSettled).toBe(false);
      expect(subscribe).not.toHaveBeenCalled();
      await act(async () => {
        body.resolve(new TextEncoder().encode('[]'));
        await agents;
      });
      await waitFor(() => expect(subscribe).toHaveBeenCalledOnce());
    } finally {
      unmount();
    }
  });
});
