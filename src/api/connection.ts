import { useSyncExternalStore } from 'react';

/** Thrown when the Hermes API cannot be reached at all (network failure), as opposed to an HTTP error. */
export class HermesUnreachableError extends Error {
  readonly url: string;

  constructor(url: string) {
    super(`Can't reach Hermes at ${url}`);
    this.name = 'HermesUnreachableError';
    this.url = url;
  }
}

export interface ConnectionState {
  /** False once a request to Hermes failed at the network level, until a later request succeeds. */
  reachable: boolean;
  /** Epoch ms of the last successful response from Hermes in this session, or null if none yet. */
  lastContactAt: number | null;
  /** Base URL that failed, when unreachable. */
  url: string | null;
}

let state: ConnectionState = { reachable: true, lastContactAt: null, url: null };
const listeners = new Set<() => void>();

function publish(next: ConnectionState) {
  state = next;
  listeners.forEach((fn) => fn());
}

/** Called after any HTTP response from Hermes, whatever its status. */
export function recordContact(): void {
  if (state.reachable && state.lastContactAt !== null) {
    state = { ...state, lastContactAt: Date.now() };
    return;
  }
  publish({ reachable: true, lastContactAt: Date.now(), url: null });
}

/** Called when a request fails at the network level. */
export function recordUnreachable(url: string): void {
  if (!state.reachable && state.url === url) return;
  publish({ reachable: false, lastContactAt: state.lastContactAt, url });
}

export function getConnection(): ConnectionState {
  return state;
}

export function subscribeConnection(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Reactive connection state for components. */
export function useConnection(): ConnectionState {
  return useSyncExternalStore(subscribeConnection, getConnection, getConnection);
}

/** Test helper: returns the tracker to its initial state. */
export function resetConnectionForTests(): void {
  publish({ reachable: true, lastContactAt: null, url: null });
}
