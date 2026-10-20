import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { hermesApi } from '../api/client';
import { useJobs } from '../api/hooks';
import { loadOnce, resetInFlightRequests } from '../api/inFlight';
import { useConsoleStore } from '../stores/useConsoleStore';

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
};

beforeEach(() => {
  resetInFlightRequests();
  vi.restoreAllMocks();
});

describe('request sharing (M7 efficiency)', () => {
  it('concurrent loads with the same share key make one request', async () => {
    const calls = vi.fn(() => Promise.resolve('value'));
    const [a, b] = [loadOnce('k', calls), loadOnce('k', calls)];
    expect(calls).toHaveBeenCalledTimes(1);
    await expect(Promise.all([a, b])).resolves.toEqual(['value', 'value']);
  });

  it('a settled request is forgotten, so a later load goes out again', async () => {
    const calls = vi.fn(() => Promise.resolve(1));
    await loadOnce('k', calls);
    await loadOnce('k', calls);
    expect(calls).toHaveBeenCalledTimes(2);
  });

  it('mounted hooks with the same state share one request', async () => {
    const getJobs = vi.spyOn(hermesApi, 'getJobs').mockResolvedValue([]);
    renderHook(() => useJobs());
    renderHook(() => useJobs());
    renderHook(() => useJobs());
    await waitFor(() => expect(getJobs).toHaveBeenCalled());
    expect(getJobs).toHaveBeenCalledTimes(1);
  });

  it('a live change still sends a new request while an earlier one is in flight', async () => {
    const first = deferred<never[]>();
    const getJobs = vi
      .spyOn(hermesApi, 'getJobs')
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce([]);
    renderHook(() => useJobs());
    expect(getJobs).toHaveBeenCalledTimes(1);
    // An event arrives while the first request is still out: its data may predate the event, so it must refetch.
    act(() => {
      useConsoleStore.setState({ jobRuntimeVersion: useConsoleStore.getState().jobRuntimeVersion + 1 });
    });
    await waitFor(() => expect(getJobs).toHaveBeenCalledTimes(2));
    first.resolve([]);
  });
});
