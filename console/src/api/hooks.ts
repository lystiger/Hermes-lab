import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { hermesApi, isRealApiMode } from './client';
import { EventSubscription } from './contracts';
import {
  AgentId,
  SettingItem,
  ActorRef,
  TraceEvent,
  HealthStatus,
  Thread,
  Message,
  MailboxEntry,
  AgentModelsMap
} from './types';
import { resolveActorPresentation } from './actors';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { isExecutionEvent } from '../stores/executionReducer';
import { loadOnce } from './inFlight';

export function useHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { setBackendHealth, setConnectionStatus } = useConsoleStore();

  const checkHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await hermesApi.getHealth();
      setHealth(data);
      setBackendHealth(data);
      setConnectionStatus('CONNECTED');
      setError(null);
    } catch (err) {
      setError(err as Error);
      setConnectionStatus('DISCONNECTED');
    } finally {
      setLoading(false);
    }
  }, [setBackendHealth, setConnectionStatus]);

  useEffect(() => {
    checkHealth();
    // Poll health periodically every 30s
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  return { health, loading, error, refetch: checkHealth };
}

/** Result of one keyed resource. Data survives only refreshes of the same key; a different key starts empty. */
interface ResourceState<T> {
  key: string | null;
  data: T | null;
  error: Error | null;
  updatedAt: number | null;
  loading: boolean;
}

/**
 * Loads one resource identified by `key` (for example `agent:claude` or `job:<id>`) and re-runs when `deps`
 * change. Correctness rules (M5 F1, F2):
 * - Data from another key is never returned. Changing key clears it at once.
 * - Only the newest request for the current key may write state. An older response that resolves later is dropped.
 * - A failed refresh of the same key keeps the last good data alongside the error, so the UI can say it is stale.
 */
export function useResource<T>(key: string | null, load: (() => Promise<T>) | null, deps: unknown[]) {
  const [state, setState] = useState<ResourceState<T>>({ key, data: null, error: null, updatedAt: null, loading: load !== null });
  const [attempt, setAttempt] = useState(0);
  // Tokens increase with each request. A response is applied only if it is newer than the last one applied, so a
  // request that is superseded by a refresh still lands when it is the newest to finish. Live events can restart a
  // load many times a second; requiring the very latest request to finish would starve the screen (M7).
  const latest = useRef(0);
  const applied = useRef(0);
  // A response that arrives after the component has unmounted has nowhere to go; it is dropped.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const refetch = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const token = ++latest.current;
    if (!load) {
      setState({ key, data: null, error: null, updatedAt: null, loading: false });
      return;
    }
    setState((prev) => {
      const same = prev.key === key;
      return { key, data: same ? prev.data : null, error: same ? prev.error : null, updatedAt: same ? prev.updatedAt : null, loading: true };
    });
    (key ? loadOnce(JSON.stringify([key, attempt, ...deps]), load) : load()).then(
      (result) => {
        if (!alive.current || token <= applied.current) return;
        applied.current = token;
        setState({ key, data: result, error: null, updatedAt: Date.now(), loading: false });
      },
      (err) => {
        if (!alive.current || token <= applied.current) return;
        applied.current = token;
        setState((prev) => ({ key, data: prev.key === key ? prev.data : null, error: err as Error, updatedAt: prev.key === key ? prev.updatedAt : null, loading: false }));
      }
    );
    // The caller's deps decide when to refetch; the loader is rebuilt on each render.
  }, [key, attempt, ...deps]);

  // State left over from another key is never shown.
  const current: ResourceState<T> = state.key === key ? state : { key, data: null, error: null, updatedAt: null, loading: load !== null };
  return {
    data: current.data,
    loading: current.loading,
    error: current.error,
    updatedAt: current.updatedAt,
    /** True when the last good data is still shown while the latest refresh has failed. */
    stale: current.data !== null && current.error !== null,
    refetch
  };
}

export function useAgents() {
  const { agentRuntimeVersion, agentRuntimeStatuses } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource('agents', () => hermesApi.getAgents(), [agentRuntimeVersion]);
  const baseAgents = data ?? [];

  // Reactive overlay: live statuses from SSE for the same agent identity only.
  const agents = useMemo(() => {
    return baseAgents.map((ag) => {
      const liveOverlay = agentRuntimeStatuses[ag.id.toLowerCase()];
      if (!liveOverlay) return ag;
      return {
        ...ag,
        status: liveOverlay.status || ag.status,
        currentTask: liveOverlay.currentTask !== undefined ? liveOverlay.currentTask : ag.currentTask
      };
    });
  }, [baseAgents, agentRuntimeStatuses]);

  return { agents, loading, error, updatedAt, stale, refetch };
}

export function useAgent(id?: AgentId) {
  const { agentRuntimeStatuses, agentRuntimeVersion } = useConsoleStore();
  const key = id ? `agent:${id.toLowerCase()}` : null;
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    key,
    id ? () => hermesApi.getAgent(id) : null,
    [id, agentRuntimeVersion]
  );
  // The response must be the agent that was asked for; anything else is not shown.
  const base = data && id && data.id.toLowerCase() === id.toLowerCase() ? data : null;

  const agent = useMemo(() => {
    if (!base || !id) return base;
    const liveOverlay = agentRuntimeStatuses[id.toLowerCase()];
    if (!liveOverlay) return base;
    return {
      ...base,
      status: liveOverlay.status || base.status,
      currentTask: liveOverlay.currentTask !== undefined ? liveOverlay.currentTask : base.currentTask
    };
  }, [base, id, agentRuntimeStatuses]);

  return { agent, loading, error, updatedAt, stale, refetch };
}

export function useAgentModels() {
  const { agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource<AgentModelsMap>(
    'agent-models',
    () => hermesApi.getAgentModels(),
    [agentRuntimeVersion]
  );
  return { models: data, loading, error, updatedAt, stale, refetch };
}

export function useJobs() {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource('jobs', () => hermesApi.getJobs(), [jobRuntimeVersion]);
  return { jobs: data ?? [], loading, error, updatedAt, stale, refetch };
}

export function useJob(id: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    id ? `job:${id}` : null,
    id ? () => hermesApi.getJob(id) : null,
    [id, jobRuntimeVersion]
  );
  // A detail is shown only for the job that was asked for.
  const job = data && id && data.id === id ? data : null;
  return { job, loading, error, updatedAt, stale, refetch };
}

export function usePipeline() {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource('pipeline', () => hermesApi.getPipeline(), [jobRuntimeVersion]);
  return { pipeline: data ?? [], loading, error, updatedAt, stale, refetch };
}

export function useTelemetry() {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    'telemetry',
    async () => {
      const [telemetry, projections] = await Promise.all([hermesApi.getTelemetry(), hermesApi.getProjections()]);
      return { telemetry, projections };
    },
    [jobRuntimeVersion, agentRuntimeVersion]
  );
  return {
    telemetry: data?.telemetry ?? null,
    projections: data?.projections ?? [],
    loading,
    error,
    updatedAt,
    stale,
    refetch
  };
}

/** Capacity telemetry. Totals are since runtime start; they refresh on job and agent activity. */
export function useCapacityTelemetry() {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    'capacity',
    () => hermesApi.getCapacityTelemetry(),
    [jobRuntimeVersion, agentRuntimeVersion]
  );
  return { capacity: data, loading, error, updatedAt, stale, refetch };
}

/** Per-agent usage limits. The backend computes the numbers; this refreshes them every 60 seconds. */
export function useAgentLimits() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000);
    return () => clearInterval(id);
  }, []);
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    'agent-limits',
    () => hermesApi.getAgentLimits(),
    [tick]
  );
  return { limits: data, loading, error, updatedAt, stale, refetch };
}

/** Finished goal-planned runs for review. Refetched on job activity, since a run is finalized when it completes. */
export function useReviews() {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource('reviews', () => hermesApi.getReviews(), [jobRuntimeVersion]);
  return { reviews: data ?? [], loading, error, updatedAt, stale, refetch };
}

/** Token telemetry for one job. Keyed by job, so another job's totals are never shown. */
export function useJobTelemetry(jobId: string | null) {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    jobId ? `job-telemetry:${jobId}` : null,
    jobId ? () => hermesApi.getJobTelemetry(jobId) : null,
    [jobId, jobRuntimeVersion, agentRuntimeVersion]
  );
  return { telemetry: data, loading, error, updatedAt, stale, refetch };
}

export function useJobTasks(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    jobId ? `job-tasks:${jobId}` : null,
    jobId ? () => hermesApi.getJobTasks(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { tasks: data ?? [], loading, error, updatedAt, stale, refetch };
}

export function useJobRuns(jobId: string | null) {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    jobId ? `job-runs:${jobId}` : null,
    jobId ? () => hermesApi.getJobRuns(jobId) : null,
    [jobId, jobRuntimeVersion, agentRuntimeVersion]
  );
  return { runs: data ?? [], loading, error, updatedAt, stale, refetch };
}

export function useJobObservations(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    jobId ? `job-observations:${jobId}` : null,
    jobId ? () => hermesApi.getJobObservations(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { observations: data ?? [], loading, error, updatedAt, stale, refetch };
}

/** Durable job history. Live events for the job are merged on top by the caller. */
export function useJobEvents(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    jobId ? `job-events:${jobId}` : null,
    jobId ? () => hermesApi.getJobEvents(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { events: data ?? [], loading, error, updatedAt, stale, refetch };
}

/** Recoverable jobs, read-only. */
export function useRecoverableJobs() {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, stale, refetch } = useResource(
    'recoverable',
    () => hermesApi.getRecoverableJobs(),
    [jobRuntimeVersion]
  );
  return { jobs: data ?? [], loading, error, updatedAt, stale, refetch };
}

export function useSettings() {
  const { data, loading, error, updatedAt, stale, refetch } = useResource<{ runtime: SettingItem[]; policy: SettingItem[] }>(
    'settings',
    () => hermesApi.getSettings(),
    []
  );

  return {
    settings: data ?? { runtime: [], policy: [] },
    loading,
    error,
    updatedAt,
    stale,
    refetch
  };
}

export function useEventStream() {
  const { addTraceEvent, setInitialEvents, setConnectionStatus, setBackendHealth } = useConsoleStore();

  useEffect(() => {
    let isSubscribed = true;
    let eventSub: EventSubscription | null = null;
    const startup = new AbortController();
    // Set when the SSE connection errors; the next delivered event proves it is back, so state is resynced.
    let streamDropped = false;

    async function initStream() {
      // 1. Initial Health Check
      try {
        const health = await hermesApi.getHealth();
        if (isSubscribed) {
          setBackendHealth(health);
          setConnectionStatus('CONNECTED');
        }
      } catch {
        if (isSubscribed && isRealApiMode) {
          setConnectionStatus('DISCONNECTED');
        }
      }

      // 2. Load historical events from API first (Task 9 & Item 2: Establish cursor = newest event ID)
      let initialCursor: string | undefined;
      const loadHistory = async () => {
        try {
          const history = await hermesApi.getTraceEvents(100);
          if (isSubscribed) {
            setInitialEvents(history);
            // Close the snapshot -> stream gap: execution events that happened after the snapshot but before
            // the SSE cursor only exist in this history. Replay them oldest first; the store dedupes by id and
            // holds them behind any snapshot still in flight.
            const executionStore = useExecutionStore.getState();
            [...history]
              .filter((e) => isExecutionEvent(e))
              .sort((a, b) => a.rawTs - b.rawTs)
              .forEach((e) => executionStore.applyEvent(e));
            if (history.length > 0) {
              // Find newest event by highest raw timestamp (Item 2)
              const newestEvent = history.reduce((prev, curr) => (curr.rawTs > prev.rawTs ? curr : prev));
              initialCursor = newestEvent.id;
            }
          }
        } catch {
          if (isSubscribed && isRealApiMode) {
            setConnectionStatus('DISCONNECTED');
          }
        }
      };
      await loadHistory();

      // Let the initial HTTP burst release its connections before reserving one for SSE.
      await hermesApi.waitForIdle?.(startup.signal);
      // Without a cursor the stream starts at "now", so events from the wait would be lost; reload to get one.
      if (!initialCursor && isSubscribed && !startup.signal.aborted) await loadHistory();

      // 3. Open SSE stream starting strictly after newest historical event
      if (isSubscribed) {
        eventSub = hermesApi.subscribeEvents(
          (evt: TraceEvent) => {
            if (isSubscribed) {
              addTraceEvent(evt);
              setConnectionStatus('CONNECTED');
              if (streamDropped) {
                // Events were missed while disconnected: reset execution state to a fresh snapshot,
                // and refetch identity and telemetry that events would otherwise have updated.
                streamDropped = false;
                void useExecutionStore.getState().refreshSnapshot();
                useConsoleStore.getState().markRuntimeResynced();
              }
              if (isExecutionEvent(evt)) {
                useExecutionStore.getState().applyEvent(evt);
              }
            }
          },
          () => {
            streamDropped = true;
            if (isSubscribed && isRealApiMode) {
              setConnectionStatus('DISCONNECTED');
            }
          },
          initialCursor
        );
      }
    }

    initStream();

    return () => {
      isSubscribed = false;
      startup.abort();
      if (eventSub) {
        eventSub.unsubscribe();
      }
    };
  }, [addTraceEvent, setInitialEvents, setConnectionStatus, setBackendHealth]);
}

/** Loads the D-009 execution snapshot once on mount. Live `execution.*` events are applied by useEventStream. */
export function useExecutionSnapshotLoader() {
  useEffect(() => {
    void useExecutionStore.getState().refreshSnapshot();
  }, []);
}

/** Execution view (snapshot + events) and load status for components. */
export function useExecution() {
  const view = useExecutionStore((s) => s.view);
  const snapshotStatus = useExecutionStore((s) => s.snapshotStatus);
  const snapshotError = useExecutionStore((s) => s.snapshotError);
  const snapshotLoadedAt = useExecutionStore((s) => s.snapshotLoadedAt);
  const refresh = useExecutionStore((s) => s.refreshSnapshot);
  return { view, snapshotStatus, snapshotError, snapshotLoadedAt, refresh };
}

export function useActorPresentation(actorIdentifier: string): ActorRef {
  const { agents } = useAgents();
  return resolveActorPresentation(actorIdentifier, agents);
}

export function useThreads(jobId?: string, participant?: string) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { messageRuntimeVersion, jobRuntimeVersion } = useConsoleStore();
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const fetchThreads = useCallback(async () => {
    try {
      if (alive.current) setLoading(true);
      const data = await hermesApi.getThreads(jobId, participant);
      if (alive.current) {
        setThreads(data);
        setError(null);
      }
    } catch (err) {
      if (alive.current) setError(err as Error);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [jobId, participant]);

  useEffect(() => {
    fetchThreads();
  }, [fetchThreads, messageRuntimeVersion, jobRuntimeVersion]);

  return { threads, loading, error, refetch: fetchThreads };
}

export function useThread(threadId: string | null) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { messageRuntimeVersion } = useConsoleStore();

  const fetchThread = useCallback(async (id: string) => {
    try {
      setLoading(true);
      const data = await hermesApi.getThread(id);
      setThread(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (threadId) {
      fetchThread(threadId);
    } else {
      setThread(null);
    }
  }, [threadId, fetchThread, messageRuntimeVersion]);

  return { thread, loading, error, refetch: () => threadId && fetchThread(threadId) };
}

export function useMessages(threadId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { messageRuntimeVersion } = useConsoleStore();

  const fetchMessages = useCallback(async (id: string) => {
    try {
      setLoading(true);
      const data = await hermesApi.getMessages(id);
      setMessages(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (threadId) {
      fetchMessages(threadId);
    } else {
      setMessages([]);
    }
  }, [threadId, fetchMessages, messageRuntimeVersion]);

  return { messages, loading, error, refetch: () => threadId && fetchMessages(threadId) };
}

export function useAgentInbox(agentId?: string, state?: string) {
  const [inbox, setInbox] = useState<MailboxEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { messageRuntimeVersion } = useConsoleStore();

  const fetchInbox = useCallback(async (targetAgent: string) => {
    try {
      setLoading(true);
      const data = await hermesApi.getAgentInbox(targetAgent, state);
      setInbox(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [state]);

  useEffect(() => {
    if (agentId) {
      fetchInbox(agentId);
    } else {
      setInbox([]);
    }
  }, [agentId, fetchInbox, messageRuntimeVersion]);

  return { inbox, loading, error, refetch: () => agentId && fetchInbox(agentId) };
}
