import { useState, useEffect, useCallback, useMemo } from 'react';
import { hermesApi, isRealApiMode } from './client';
import { EventSubscription } from './contracts';
import {
  AgentSummary,
  AgentDetail,
  AgentId,
  Job,
  JobDetail,
  PipelineStep,
  ProjectionItem,
  SettingItem,
  OverviewTelemetry,
  ActorRef,
  TraceEvent,
  HealthStatus,
  Thread,
  Message,
  MailboxEntry
} from './types';
import { resolveActorPresentation } from './actors';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useExecutionStore } from '../stores/useExecutionStore';
import { isExecutionEvent } from '../stores/executionReducer';

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

export function useAgents() {
  const [baseAgents, setBaseAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const { setConnectionStatus, agentRuntimeStatuses, agentRuntimeVersion } = useConsoleStore();

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await hermesApi.getAgents();
      setBaseAgents(data);
      setUpdatedAt(Date.now());
      if (isRealApiMode) {
        setConnectionStatus('CONNECTED');
      }
      setError(null);
    } catch (err) {
      setError(err as Error);
      if (isRealApiMode) {
        setConnectionStatus('DISCONNECTED');
      }
    } finally {
      setLoading(false);
    }
  }, [setConnectionStatus]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents, agentRuntimeVersion]);

  // Reactive overlay: updates dynamically whenever SSE events change active statuses (Item 1)
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

  return { agents, loading, error, updatedAt, refetch: fetchAgents };
}

export function useAgent(id?: AgentId) {
  const [baseAgent, setBaseAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { agentRuntimeStatuses } = useConsoleStore();

  const fetchAgent = useCallback(async (targetId: AgentId) => {
    try {
      setLoading(true);
      const data = await hermesApi.getAgent(targetId);
      setBaseAgent(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (id) {
      fetchAgent(id);
    }
  }, [id, fetchAgent]);

  // Reactive overlay for single agent inspection (Item 1)
  const agent = useMemo(() => {
    if (!baseAgent || !id) return baseAgent;
    const liveOverlay = agentRuntimeStatuses[id.toLowerCase()];
    if (!liveOverlay) return baseAgent;
    return {
      ...baseAgent,
      status: liveOverlay.status || baseAgent.status,
      currentTask: liveOverlay.currentTask !== undefined ? liveOverlay.currentTask : baseAgent.currentTask
    };
  }, [baseAgent, id, agentRuntimeStatuses]);

  return { agent, loading, error, refetch: () => id && fetchAgent(id) };
}

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await hermesApi.getJobs();
      setJobs(data);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs, jobRuntimeVersion]);

  return { jobs, loading, error, updatedAt, refetch: fetchJobs };
}

export function useJob(id: string | null) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchJob = useCallback(async (jobId: string) => {
    try {
      setLoading(true);
      const data = await hermesApi.getJob(jobId);
      setJob(data);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (id) {
      fetchJob(id);
    } else {
      setJob(null);
    }
  }, [id, fetchJob, jobRuntimeVersion]);

  return { job, loading, error, updatedAt, refetch: () => id && fetchJob(id) };
}

export function usePipeline() {
  const [pipeline, setPipeline] = useState<PipelineStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchPipeline = useCallback(async () => {
    try {
      setLoading(true);
      const data = await hermesApi.getPipeline();
      setPipeline(data);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPipeline();
  }, [fetchPipeline, jobRuntimeVersion]);

  return { pipeline, loading, error, updatedAt, refetch: fetchPipeline };
}

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState<OverviewTelemetry | null>(null);
  const [projections, setProjections] = useState<ProjectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [tel, proj] = await Promise.all([hermesApi.getTelemetry(), hermesApi.getProjections()]);
      setTelemetry(tel);
      setProjections(proj);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, jobRuntimeVersion, agentRuntimeVersion]);

  return { telemetry, projections, loading, error, updatedAt, refetch: load };
}

/**
 * Loads one resource whenever `load` is provided and any dependency changes. A null loader means nothing
 * is requested (for example, no job selected). Failures are kept as errors; the last good data is retained.
 */
export function useResource<T>(load: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(load !== null);
  const [error, setError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const refetch = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    if (!load) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    load()
      .then((result) => {
        if (!active) return;
        setData(result);
        setUpdatedAt(Date.now());
        setError(null);
      })
      .catch((err) => {
        if (active) setError(err as Error);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // The loader is rebuilt on each render; the caller's deps decide when to refetch.
  }, [attempt, ...deps]);

  return { data, loading, error, updatedAt, refetch };
}

/** Capacity telemetry. Totals are since runtime start; they refresh on job and agent activity. */
export function useCapacityTelemetry() {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    () => hermesApi.getCapacityTelemetry(),
    [jobRuntimeVersion, agentRuntimeVersion]
  );
  return { capacity: data, loading, error, updatedAt, refetch };
}

/** Token telemetry for one job. */
export function useJobTelemetry(jobId: string | null) {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    jobId ? () => hermesApi.getJobTelemetry(jobId) : null,
    [jobId, jobRuntimeVersion, agentRuntimeVersion]
  );
  return { telemetry: data, loading, error, updatedAt, refetch };
}

export function useJobTasks(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    jobId ? () => hermesApi.getJobTasks(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { tasks: data ?? [], loading, error, updatedAt, refetch };
}

export function useJobRuns(jobId: string | null) {
  const { jobRuntimeVersion, agentRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    jobId ? () => hermesApi.getJobRuns(jobId) : null,
    [jobId, jobRuntimeVersion, agentRuntimeVersion]
  );
  return { runs: data ?? [], loading, error, updatedAt, refetch };
}

export function useJobObservations(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    jobId ? () => hermesApi.getJobObservations(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { observations: data ?? [], loading, error, updatedAt, refetch };
}

/** Durable job history. Live events for the job are merged on top by the caller. */
export function useJobEvents(jobId: string | null) {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    jobId ? () => hermesApi.getJobEvents(jobId) : null,
    [jobId, jobRuntimeVersion]
  );
  return { events: data ?? [], loading, error, updatedAt, refetch };
}

/** Recoverable jobs, read-only. */
export function useRecoverableJobs() {
  const { jobRuntimeVersion } = useConsoleStore();
  const { data, loading, error, updatedAt, refetch } = useResource(
    () => hermesApi.getRecoverableJobs(),
    [jobRuntimeVersion]
  );
  return { jobs: data ?? [], loading, error, updatedAt, refetch };
}

export function useSettings() {
  const [settings, setSettings] = useState<{ runtime: SettingItem[]; policy: SettingItem[] }>({
    runtime: [],
    policy: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    hermesApi.getSettings().then(setSettings).finally(() => setLoading(false));
  }, []);

  return { settings, loading };
}

export function useEventStream() {
  const { addTraceEvent, setInitialEvents, setConnectionStatus, setBackendHealth } = useConsoleStore();

  useEffect(() => {
    let isSubscribed = true;
    let eventSub: EventSubscription | null = null;
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

  const fetchThreads = useCallback(async () => {
    try {
      setLoading(true);
      const data = await hermesApi.getThreads(jobId, participant);
      setThreads(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
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
