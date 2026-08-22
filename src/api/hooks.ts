import { useState, useEffect, useCallback } from 'react';
import { lysStackApi } from './client';
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
  TraceEvent
} from './types';
import { resolveActorPresentation } from './actors';
import { useConsoleStore } from '../stores/useConsoleStore';

export function useAgents() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await lysStackApi.getAgents();
      setAgents(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  return { agents, loading, error, refetch: fetchAgents };
}

export function useAgent(id?: AgentId) {
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchAgent = useCallback(async (targetId: AgentId) => {
    try {
      setLoading(true);
      const data = await lysStackApi.getAgent(targetId);
      setAgent(data);
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

  return { agent, loading, error, refetch: () => id && fetchAgent(id) };
}

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

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
  }, [fetchJobs]);

  return { jobs, loading, error, refetch: fetchJobs };
}

export function useJob(id: string | null) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

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
  }, [id, fetchJob]);

  return { job, loading, error };
}

export function usePipeline() {
  const [pipeline, setPipeline] = useState<PipelineStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

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
  }, [fetchPipeline]);

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
  const { addTraceEvent, setInitialEvents } = useConsoleStore();

  useEffect(() => {
    let isSubscribed = true;

    // Load initial events from API
    lysStackApi.getTraceEvents().then((initial) => {
      if (isSubscribed) {
        setInitialEvents(initial);
      }
    });

    // Subscribe to live stream
    const sub = lysStackApi.subscribeEvents((evt: TraceEvent) => {
      if (isSubscribed) {
        addTraceEvent(evt);
      }
    });

    return () => {
      isSubscribed = false;
      sub.unsubscribe();
    };
  }, [addTraceEvent, setInitialEvents]);
}

export function useActorPresentation(actorIdentifier: string): ActorRef {
  const { agents } = useAgents();
  return resolveActorPresentation(actorIdentifier, agents);
}
