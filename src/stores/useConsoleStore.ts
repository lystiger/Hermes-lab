import { create } from 'zustand';
import { TraceEvent, AgentSummary, AgentDetail, ConnectionStatus, HealthStatus, AgentStatus } from '../api/types';
import { isRealApiMode } from '../api/client';

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
  // Connection State to LysStack Backend
  connectionStatus: ConnectionStatus;
  backendHealth: HealthStatus | null;

  // Reactive Runtime State
  agentRuntimeStatuses: Record<string, AgentRuntimeState>;
  jobRuntimeVersion: number;
  messageRuntimeVersion: number;

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
  clock: string;
  elapsed: string;
  tokensToday: string;
  jobTokens: string;
  hardenTokens: string;
  
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
}

const baseTs = 10 * 3600 + 42 * 60 + 16;

export const useConsoleStore = create<ConsoleUIState>((set, get) => ({
  connectionStatus: isRealApiMode ? 'CONNECTING' : 'CONNECTED',
  backendHealth: null,
  agentRuntimeStatuses: {},
  jobRuntimeVersion: 0,
  messageRuntimeVersion: 0,
  selectedAgentId: 'claude',
  activeModalJobId: null,
  activeDossierAgent: null,
  qFilter: 'All',
  eFilter: 'All',
  liveMotion: true,
  ambient3d: true,
  portraits: 'both',
  
  tick: 0,
  clock: '10:42',
  elapsed: '08:41',
  tokensToday: isRealApiMode ? '—' : '284K',
  jobTokens: isRealApiMode ? '—' : '44.1k',
  hardenTokens: isRealApiMode ? '—' : '13.7k',
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

      return {
        allEvents: nextEvents,
        agentRuntimeStatuses: nextStatuses,
        jobRuntimeVersion: nextJobVersion,
        messageRuntimeVersion: nextMessageVersion
      };
    }),

  tickClock: () => {
    const state = get();
    const nextTick = state.tick + 1;
    const elapsedS = 521 + nextTick;
    const elapsed = `${pad(Math.floor(elapsedS / 60), 2)}:${pad(elapsedS % 60, 2)}`;
    const clockS = baseTs + nextTick;
    const clock = `${pad(Math.floor(clockS / 3600), 2)}:${pad(Math.floor(clockS / 60) % 60, 2)}`;

    // In simulated mock mode only, advance demo counters
    if (!isRealApiMode) {
      const jobTokens = `${((44100 + nextTick * 41) / 1000).toFixed(1)}k`;
      const hardenTokens = `${((13700 + nextTick * 41) / 1000).toFixed(1)}k`;
      const tokensToday = `${284 + Math.floor(nextTick * 0.06)}K`;

      set({
        tick: nextTick,
        clock,
        elapsed,
        jobTokens,
        hardenTokens,
        tokensToday
      });
    } else {
      // In real HTTP mode, keep clock ticking without fabricating fake telemetry numbers
      set({
        tick: nextTick,
        clock,
        elapsed
      });
    }
  }
}));

// Background client-only clock ticker
if (typeof window !== 'undefined') {
  setInterval(() => {
    useConsoleStore.getState().tickClock();
  }, 1000);
}
