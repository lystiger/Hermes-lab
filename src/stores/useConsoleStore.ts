import { create } from 'zustand';
import { TraceEvent, AgentSummary, AgentDetail, ConnectionStatus, HealthStatus, AgentStatus } from '../api/types';
import { isMockMode } from '../api/client';
import { prefersReducedMotion } from '../theme/motion';

function pad(n: number, w: number): string {
  return String(n).padStart(w, '0');
}

export function fmtTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor(sec / 60) % 60;
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
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
      allEvents: state.allEvents.length === 0 ? events : state.allEvents
    })),

  addTraceEvent: (event) =>
    set((state) => {
      // 1. Deduplicate by event ID
      const alreadyExists = state.allEvents.some((e) => e.id === event.id);
      const nextEvents = alreadyExists
        ? state.allEvents
        : [event, ...state.allEvents].slice(0, 150);

      // 2. Reactively reduce agent status from live runtime events
      let nextStatuses = state.agentRuntimeStatuses;
      const sourceId = event.source?.id?.toLowerCase();

      if (sourceId && event.source.kind === 'agent') {
        if (event.kind === 'agent.started') {
          nextStatuses = {
            ...nextStatuses,
            [sourceId]: {
              status: 'RUNNING',
              currentTask: event.metadata?.task || event.metadata?.phase || event.detail
            }
          };
        } else if (event.kind === 'agent.finished') {
          nextStatuses = {
            ...nextStatuses,
            [sourceId]: {
              status: 'IDLE',
              currentTask: undefined
            }
          };
        } else if (event.kind === 'agent.failed') {
          nextStatuses = {
            ...nextStatuses,
            [sourceId]: {
              status: 'ERROR',
              currentTask: undefined
            }
          };
        }
      }

      // 3. Reactively bump job/message runtime versions on runtime events
      const isJobEvent = event.kind.startsWith('job.') || event.kind.startsWith('phase.');
      const nextJobVersion = isJobEvent ? state.jobRuntimeVersion + 1 : state.jobRuntimeVersion;
      const isMessageEvent = event.kind.startsWith('message.') || event.kind.startsWith('thread.') || event.kind.startsWith('artifact.');
      const nextMessageVersion = isMessageEvent ? state.messageRuntimeVersion + 1 : state.messageRuntimeVersion;
      const nextAgentVersion = event.kind.startsWith('agent.') ? state.agentRuntimeVersion + 1 : state.agentRuntimeVersion;

      return {
        allEvents: nextEvents,
        agentRuntimeStatuses: nextStatuses,
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
