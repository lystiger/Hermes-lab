import { useState, useEffect, useCallback, useMemo } from 'react';
import { lysStackApi, isRealApiMode } from './client';
import { EventSubscription } from './contracts';
import {
  AgentSummary,
  AgentDetail,
  AgentId,
  Job,
  JobDetail,
  PipelineStep,
  ProviderQuota,
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

export function useHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { setBackendHealth, setConnectionStatus } = useConsoleStore();

  const checkHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await lysStackApi.getHealth();
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
  const { setConnectionStatus, agentRuntimeStatuses } = useConsoleStore();

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await lysStackApi.getAgents();
      setBaseAgents(data);
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
  }, [fetchAgents]);

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

  return { agents, loading, error, refetch: fetchAgents };
}

export function useAgent(id?: AgentId) {
  const [baseAgent, setBaseAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { agentRuntimeStatuses } = useConsoleStore();

  const fetchAgent = useCallback(async (targetId: AgentId) => {
    try {
      setLoading(true);
      const data = await lysStackApi.getAgent(targetId);
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
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await lysStackApi.getJobs();
      setJobs(data);
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

  return { jobs, loading, error, refetch: fetchJobs };
}

export function useJob(id: string | null) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchJob = useCallback(async (jobId: string) => {
    try {
      setLoading(true);
      const data = await lysStackApi.getJob(jobId);
      setJob(data);
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

  return { job, loading, error, refetch: () => id && fetchJob(id) };
}

export function usePipeline() {
  const [pipeline, setPipeline] = useState<PipelineStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { jobRuntimeVersion } = useConsoleStore();

  const fetchPipeline = useCallback(async () => {
    try {
      setLoading(true);
      const data = await lysStackApi.getPipeline();
      setPipeline(data);
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

  return { pipeline, loading, error, refetch: fetchPipeline };
}

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState<OverviewTelemetry | null>(null);
  const [quotas, setQuotas] = useState<ProviderQuota[]>([]);
  const [projections, setProjections] = useState<ProjectionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [tel, q, proj] = await Promise.all([
          lysStackApi.getTelemetry(),
          lysStackApi.getProviderQuotas(),
          lysStackApi.getProjections()
        ]);
        setTelemetry(tel);
        setQuotas(q);
        setProjections(proj);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return { telemetry, quotas, projections, loading };
}

export function useSettings() {
  const [settings, setSettings] = useState<{ runtime: SettingItem[]; policy: SettingItem[] }>({
    runtime: [],
    policy: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lysStackApi.getSettings().then(setSettings).finally(() => setLoading(false));
  }, []);

  return { settings, loading };
}

export function useEventStream() {
  const { addTraceEvent, setInitialEvents, setConnectionStatus, setBackendHealth } = useConsoleStore();

  useEffect(() => {
    let isSubscribed = true;
    let eventSub: EventSubscription | null = null;

    async function initStream() {
      // 1. Initial Health Check
      try {
        const health = await lysStackApi.getHealth();
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
        const history = await lysStackApi.getTraceEvents(100);
        if (isSubscribed) {
          setInitialEvents(history);
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
        eventSub = lysStackApi.subscribeEvents(
          (evt: TraceEvent) => {
            if (isSubscribed) {
              addTraceEvent(evt);
              setConnectionStatus('CONNECTED');
            }
          },
          () => {
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
      const data = await lysStackApi.getThreads(jobId, participant);
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
      const data = await lysStackApi.getThread(id);
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
      const data = await lysStackApi.getMessages(id);
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
      const data = await lysStackApi.getAgentInbox(targetAgent, state);
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
