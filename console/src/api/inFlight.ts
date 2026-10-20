/**
 * Requests in flight, by share key (key + deps + refetch count). Components that load the same resource for the
 * same state share one request instead of each sending their own (the Overview alone mounted eight job loaders).
 * The deps are part of the share key, so a live change (a version bump) always sends a new request, even while an
 * earlier one is still in flight. An entry is removed when its request settles.
 *
 * This lives in its own module so the test setup can reset it without loading the API client.
 */
const inFlight = new Map<string, Promise<unknown>>();

export function loadOnce<T>(shareKey: string, load: () => Promise<T>): Promise<T> {
  const existing = inFlight.get(shareKey);
  if (existing) return existing as Promise<T>;
  const request = load().finally(() => inFlight.delete(shareKey));
  inFlight.set(shareKey, request);
  return request;
}

/** Forgets requests that have not settled. Tests use it so a request that never resolves cannot leak into the next test. */
export function resetInFlightRequests(): void {
  inFlight.clear();
}
