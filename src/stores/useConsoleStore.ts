import { useState, useEffect, useCallback, useMemo } from 'react';
import { AgentData, JobItem, PipelineStep, TraceEvent, ProviderQuota, ProjectionItem, SettingItem } from '../api/types';
import { AGENTS_MAP, INITIAL_QUEUE, INITIAL_PIPELINE, SEED_EVENTS, POOL_EVENTS, PROVIDER_QUOTAS, PROJECTIONS, SET_RUNTIME_DATA, SET_POLICY_DATA, ACTIVE_JOB_CHANGED_FILES, AGENT_COLOR_MAP } from '../api/mockData';

function pad(n: number, w: number): string {
  let s = String(n);
  while (s.length < w) s = '0' + s;
  return s;
}

export function fmtTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor(sec / 60) % 60;
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

// Global Store State Singleton to preserve timer across route transitions
let globalTick = 0;
const baseTs = 10 * 3600 + 42 * 60 + 16;
let globalEvents: TraceEvent[] = SEED_EVENTS.map((e, idx) => ({
  id: `seed-${idx}`,
  ts: fmtTs(baseTs + e.t),
  rawTs: baseTs + e.t,
  agent: e.a,
  kind: e.k,
  detail: e.d,
  dur: e.dur || '—',
  job: '#142'
})).reverse();

let globalLastTs = baseTs + 31.4;
const subscribers = new Set<() => void>();

function notify() {
  subscribers.forEach(fn => fn());
}

if (typeof window !== 'undefined') {
  setInterval(() => {
    globalTick += 1;
    if (globalTick % 2 === 1) {
      const p = POOL_EVENTS[Math.floor(globalTick / 2) % POOL_EVENTS.length];
      const ts = globalLastTs + 0.4 + ((globalTick * 37) % 130) / 100;
      const newEvent: TraceEvent = {
        id: `evt-${globalTick}-${Date.now()}`,
        ts: fmtTs(ts),
        rawTs: ts,
        agent: p.a,
        kind: p.k,
        detail: p.d,
        dur: p.dur || '—',
        job: '#142'
      };
      globalEvents = [newEvent, ...globalEvents].slice(0, 100);
      globalLastTs = ts;
    }
    notify();
  }, 1000);
}

export function useConsoleStore() {
  const [, setTick] = useState(0);

  useEffect(() => {
    const sub = () => setTick(t => t + 1);
    subscribers.add(sub);
    return () => {
      subscribers.delete(sub);
    };
  }, []);

  const [qFilter, setQFilter] = useState<string>('All');
  const [eFilter, setEFilter] = useState<string>('All');
  const [liveMotion, setLiveMotion] = useState<boolean>(true);
  const [ambient3d, setAmbient3d] = useState<boolean>(true);
  const [portraits, setPortraits] = useState<'both' | 'slots' | 'marks'>('both');
  const [selectedAgentId, setSelectedAgentId] = useState<string>('claude');
  const [activeModalJobId, setActiveModalJobId] = useState<string | null>(null);

  const t = globalTick;
  const elapsedS = 521 + t;
  const elapsed = `${pad(Math.floor(elapsedS / 60), 2)}:${pad(elapsedS % 60, 2)}`;
  const clockS = 10 * 3600 + 42 * 60 + 16 + t;
  const clock = `${pad(Math.floor(clockS / 3600), 2)}:${pad(Math.floor(clockS / 60) % 60, 2)}`;
  const jobTokens = `${((44100 + t * 41) / 1000).toFixed(1)}k`;
  const hardenTokens = `${((13700 + t * 41) / 1000).toFixed(1)}k`;
  const tokensToday = `${284 + Math.floor(t * 0.06)}K`;

  const agents = useMemo(() => Object.values(AGENTS_MAP), []);
  const queue = useMemo(() => INITIAL_QUEUE, []);
  const pipeline = useMemo(() => INITIAL_PIPELINE, []);
  const quotas = useMemo(() => PROVIDER_QUOTAS, []);
  const projections = useMemo(() => PROJECTIONS, []);
  const runtimeSettings = useMemo(() => SET_RUNTIME_DATA, []);
  const policySettings = useMemo(() => SET_POLICY_DATA, []);
  const changedFiles = useMemo(() => ACTIVE_JOB_CHANGED_FILES, []);

  const filteredQueue = useMemo(() => {
    if (qFilter === 'All') return queue;
    return queue.filter(q => q.status.toUpperCase() === qFilter.toUpperCase());
  }, [queue, qFilter]);

  const filteredEvents = useMemo(() => {
    return globalEvents.filter(e => {
      if (eFilter === 'All') return true;
      if (eFilter === 'Errors') return e.kind === 'error' || e.kind === 'retry' || e.kind === 'quota.warn';
      if (eFilter === 'Tools') return e.kind.startsWith('tool.');
      return e.agent.toLowerCase() === eFilter.toLowerCase();
    });
  }, [eFilter, globalEvents]);

  const activeAgent = useMemo(() => {
    return Object.values(AGENTS_MAP).find(a => a.id === selectedAgentId.toLowerCase()) || AGENTS_MAP.Claude;
  }, [selectedAgentId]);

  return {
    tick: t,
    elapsed,
    clock,
    jobTokens,
    hardenTokens,
    tokensToday,
    agents,
    activeAgent,
    selectedAgentId,
    setSelectedAgentId,
    queue: filteredQueue,
    allQueue: queue,
    pipeline,
    events: filteredEvents,
    allEvents: globalEvents,
    quotas,
    projections,
    runtimeSettings,
    policySettings,
    changedFiles,
    qFilter,
    setQFilter,
    eFilter,
    setEFilter,
    liveMotion,
    setLiveMotion,
    ambient3d,
    setAmbient3d,
    portraits,
    setPortraits,
    activeModalJobId,
    setActiveModalJobId
  };
}
