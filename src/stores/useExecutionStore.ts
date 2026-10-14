import { create } from 'zustand';
import { ExecutionSnapshot, TraceEvent } from '../api/types';
import { hermesApi } from '../api/client';
import {
  EMPTY_EXECUTION_VIEW,
  ExecutionView,
  isExecutionEvent,
  reduceExecutionEvent,
  viewFromSnapshot
} from './executionReducer';

export type ExecutionSnapshotStatus = 'idle' | 'loading' | 'ready' | 'error';

interface ExecutionStoreState {
  view: ExecutionView;
  snapshotStatus: ExecutionSnapshotStatus;
  snapshotError: string | null;
  snapshotLoadedAt: string | null;
  /** Monotonic id of the newest snapshot request; older responses are discarded. */
  latestRequest: number;
  /** Events received while a snapshot request is in flight. Null when no request is pending. */
  buffer: TraceEvent[] | null;

  applyEvent: (evt: TraceEvent) => void;
  refreshSnapshot: () => Promise<void>;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export const useExecutionStore = create<ExecutionStoreState>((set, get) => ({
  view: EMPTY_EXECUTION_VIEW,
  snapshotStatus: 'idle',
  snapshotError: null,
  snapshotLoadedAt: null,
  latestRequest: 0,
  buffer: null,

  applyEvent: (evt) => {
    if (!isExecutionEvent(evt)) return;
    const { buffer } = get();
    if (buffer) {
      // A snapshot is in flight: hold the event so it is replayed on top of the snapshot.
      set({ buffer: [...buffer, evt] });
      return;
    }
    set((state) => ({ view: reduceExecutionEvent(state.view, evt) }));
  },

  refreshSnapshot: async () => {
    const requestId = get().latestRequest + 1;
    set({ latestRequest: requestId, buffer: [], snapshotStatus: 'loading' });

    let snapshot: ExecutionSnapshot;
    try {
      snapshot = await hermesApi.getExecutionSnapshot();
    } catch (err) {
      if (get().latestRequest !== requestId) return;
      // Keep the last good view, but still apply what arrived while waiting so live state is not lost.
      set((state) => ({
        buffer: null,
        snapshotStatus: 'error',
        snapshotError: errorMessage(err),
        view: (state.buffer ?? []).reduce(reduceExecutionEvent, state.view)
      }));
      return;
    }

    if (get().latestRequest !== requestId) return;
    // Snapshot replaces the base state; events buffered during the request are replayed in arrival order.
    set((state) => ({
      view: (state.buffer ?? []).reduce(reduceExecutionEvent, viewFromSnapshot(snapshot)),
      buffer: null,
      snapshotStatus: 'ready',
      snapshotError: null,
      snapshotLoadedAt: new Date().toISOString()
    }));
  }
}));
