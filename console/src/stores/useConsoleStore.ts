import { create } from 'zustand';
import { TraceEvent, AgentSummary, AgentDetail, ConnectionStatus, HealthStatus, AgentStatus } from '../api/types';
import { isMockMode } from '../api/client';
import { prefersReducedMotion } from '../theme/motion';

function pad(n: number, w: number): string {
  return String(n).padStart(w, '0');
}

/** Event list order everywhere in the console: newest first (by epoch time, then arrival). */
export function sortNewestFirst(events: TraceEvent[]): TraceEvent[] {
  return events
    .map((event, index) => ({ event, index }))
    .sort((a, b) => b.event.rawTs - a.event.rawTs || a.index - b.index)
    .map(({ event }) => event);
}

export function fmtTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor(sec / 60) % 60;
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

/** One running sprint phase: its job plus its spec order (or name when Hermes sent no order). */
function runningPhaseKey(event: TraceEvent): string {
  const jobId = event.jobId ?? event.metadata?.jobId ?? '';
  return `${jobId}:${event.metadata?.order ?? event.metadata?.phase ?? ''}`;
}

interface AgentRuntimeState {
  status: AgentStatus;
  currentTask?: string;
}

interface ConsoleUIState {
  // Connection state to Hermes Runtime API
  connectionStatus: ConnectionStatus;
  backendHealth: HealthStatus | null;

  // Reactive Runtime State
  agentRuntimeStatuses: Record<string, AgentRuntimeState>;
  /** Sprint phases each agent is running now: agent id -> phase key -> phase name. */
  runningPhases: Record<string, Record<string, string>>;
  jobRuntimeVersion: number;
  messageRuntimeVersion: number;
  /** Bumped on agent.* events and after an SSE reconnect, so agent identity and telemetry refetch. */
  agentRuntimeVersion: number;

  // Client UI Preferences & Selection
  selectedAgentId: string;
  activeModalJobId: string | null;
  activeDossierAgent: AgentSummary | AgentDetail | null;
  qFilter: string;
  eFilter: string;
  liveMotion: boolean;
  ambient3d: boolean;
  portraits: 'both' | 'slots' | 'marks';
  
  // Real-time Visual Clock & Metrics State
  tick: number;
  /** Local wall clock in HTTP mode; demo clock in mock mode. Elapsed times are derived from job timestamps instead. */
  clock: string;
  
  // Streamed Event Trace Buffer
  allEvents: TraceEvent[];

  // Actions
  setConnectionStatus: (status: ConnectionStatus) => void;
  setBackendHealth: (health: HealthStatus | null) => void;
  updateAgentRuntimeStatus: (agentId: string, status: AgentStatus, currentTask?: string) => void;
  setSelectedAgentId: (id: string) => void;
  setActiveModalJobId: (id: string | null) => void;
  setActiveDossierAgent: (agent: AgentSummary | AgentDetail | null) => void;
  setQFilter: (filter: string) => void;
  setEFilter: (filter: string) => void;
  setLiveMotion: (enabled: boolean) => void;
  setAmbient3d: (enabled: boolean) => void;
  setPortraits: (mode: 'both' | 'slots' | 'marks') => void;
  setInitialEvents: (events: TraceEvent[]) => void;
  addTraceEvent: (event: TraceEvent) => void;
  tickClock: () => void;
  /** Called after the stream reconnects: anything derived from events may have missed updates. */
  markRuntimeResynced: () => void;
}

const baseTs = 10 * 3600 + 42 * 60 + 16;

/** Local wall clock as HH:MM, used in HTTP mode. */
function wallClock(): string {
  const d = new Date();
  return `${pad(d.getHours(), 2)}:${pad(d.getMinutes(), 2)}`;
}

export const useConsoleStore = create<ConsoleUIState>((set, get) => ({
  connectionStatus: isMockMode ? 'CONNECTED' : 'CONNECTING',
  backendHealth: null,
  agentRuntimeStatuses: {},
  runningPhases: {},
  jobRuntimeVersion: 0,
  messageRuntimeVersion: 0,
  agentRuntimeVersion: 0,
  selectedAgentId: 'claude',
  activeModalJobId: null,
  activeDossierAgent: null,
  qFilter: 'All',
  eFilter: 'All',
  // Live pulses and crawls start off when the system asks for reduced motion.
  liveMotion: !prefersReducedMotion(),
  ambient3d: true,
  portraits: 'both',
  
  tick: 0,
  clock: isMockMode ? '10:42' : wallClock(),
  allEvents: [],

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setBackendHealth: (backendHealth) => set({ backendHealth }),
  
  updateAgentRuntimeStatus: (agentId, status, currentTask) =>
    set((state) => ({
      agentRuntimeStatuses: {
        ...state.agentRuntimeStatuses,
        [agentId.toLowerCase()]: { status, currentTask }
      }
    })),

  setSelectedAgentId: (id) => set({ selectedAgentId: id.toLowerCase() }),
  setActiveModalJobId: (id) => set({ activeModalJobId: id }),
  setActiveDossierAgent: (agent) => set({ activeDossierAgent: agent }),
  setQFilter: (qFilter) => set({ qFilter }),
  setEFilter: (eFilter) => set({ eFilter }),
  setLiveMotion: (liveMotion) => set({ liveMotion }),
  setAmbient3d: (ambient3d) => set({ ambient3d }),
  setPortraits: (portraits) => set({ portraits }),

  setInitialEvents: (events) =>
    set((state) => ({
      // History arrives oldest first from the API; the console shows newest first.
      allEvents: state.allEvents.length === 0 ? sortNewestFirst(events) : state.allEvents
    })),

  addTraceEvent: (event) =>
    set((state) => {
      // 1. Deduplicate by event ID
      const alreadyExists = state.allEvents.some((e) => e.id === event.id);
      const nextEvents = alreadyExists
        ? state.allEvents
        : sortNewestFirst([event, ...state.allEvents]).slice(0, 150);

      // 2. Reactively reduce agent status from live runtime events (same rules as Hermes GET /agents)
      let nextStatuses = state.agentRuntimeStatuses;
      let nextPhases = state.runningPhases;
      const sourceId = event.source?.id?.toLowerCase();

      if (sourceId && event.source.kind === 'agent' && !alreadyExists) {
        const setStatus = (status: AgentStatus, currentTask?: string) => {
          nextStatuses = { ...nextStatuses, [sourceId]: { status, currentTask } };
        };
        const agentPhases = nextPhases[sourceId] ?? {};

        // Sprint phases: an agent in several parallel phases stays RUNNING until every one finishes.
        if (event.kind.startsWith('phase.')) {
          const key = runningPhaseKey(event);
          const remaining = { ...agentPhases };
          if (event.kind === 'phase.started') {
            remaining[key] = event.metadata?.phase || event.detail;
            setStatus('RUNNING', remaining[key]);
          } else if (event.kind === 'phase.completed' || event.kind === 'phase.failed') {
            delete remaining[key];
            const stillRunning = Object.values(remaining);
            if (event.kind === 'phase.failed') setStatus('ERROR');
            else if (stillRunning.length > 0) setStatus('RUNNING', stillRunning[0]);
            else setStatus('IDLE');
          }
          nextPhases = { ...nextPhases, [sourceId]: remaining };
        } else if (event.kind === 'agent.started') {
          setStatus('RUNNING', event.metadata?.task || event.metadata?.phase || event.detail);
        } else if (event.kind === 'agent.finished') {
          if (Object.keys(agentPhases).length === 0) setStatus('IDLE');
        } else if (event.kind === 'agent.cancelled') {
          nextPhases = { ...nextPhases, [sourceId]: {} };
          setStatus('IDLE');
        } else if (event.kind === 'agent.failed' || event.kind === 'agent.timed_out') {
          setStatus('ERROR');
        } else if (event.kind === 'agent.waiting') {
          setStatus('WAITING', event.metadata?.task || event.detail);
        } else if (event.kind === 'agent.busy') {
          setStatus('BUSY', event.metadata?.task || event.detail);
        }
      }

      // 3. Reactively bump job/message runtime versions on runtime events
      const isJobEvent = event.kind.startsWith('job.') || event.kind.startsWith('phase.') || event.kind.startsWith('task.');
      const nextJobVersion = isJobEvent ? state.jobRuntimeVersion + 1 : state.jobRuntimeVersion;
      const isMessageEvent = event.kind.startsWith('message.') || event.kind.startsWith('thread.') || event.kind.startsWith('artifact.');
      const nextMessageVersion = isMessageEvent ? state.messageRuntimeVersion + 1 : state.messageRuntimeVersion;
      const nextAgentVersion = event.kind.startsWith('agent.') ? state.agentRuntimeVersion + 1 : state.agentRuntimeVersion;

      return {
        allEvents: nextEvents,
        agentRuntimeStatuses: nextStatuses,
        runningPhases: nextPhases,
        jobRuntimeVersion: nextJobVersion,
        messageRuntimeVersion: nextMessageVersion,
        agentRuntimeVersion: nextAgentVersion
      };
    }),

  markRuntimeResynced: () =>
    set((state) => ({
      jobRuntimeVersion: state.jobRuntimeVersion + 1,
      messageRuntimeVersion: state.messageRuntimeVersion + 1,
      agentRuntimeVersion: state.agentRuntimeVersion + 1
    })),

  tickClock: () => {
    const nextTick = get().tick + 1;
    if (isMockMode) {
      const clockS = baseTs + nextTick;
      set({ tick: nextTick, clock: `${pad(Math.floor(clockS / 3600), 2)}:${pad(Math.floor(clockS / 60) % 60, 2)}` });
    } else {
      set({ tick: nextTick, clock: wallClock() });
    }
  }
}));

// Background client-only clock ticker
if (typeof window !== 'undefined') {
  setInterval(() => {
    useConsoleStore.getState().tickClock();
  }, 1000);
}
