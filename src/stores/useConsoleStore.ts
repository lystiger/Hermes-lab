import { create } from 'zustand';
import { TraceEvent, AgentSummary, AgentDetail } from '../api/types';

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

interface ConsoleUIState {
  // Client UI Preferences & Selection
  selectedAgentId: string;
  activeModalJobId: string | null;
  activeDossierAgent: AgentSummary | AgentDetail | null;
  qFilter: string;
  eFilter: string;
  liveMotion: boolean;
  ambient3d: boolean;
  portraits: 'both' | 'slots' | 'marks';
  
  // Real-time Visual Clock & Simulation State
  tick: number;
  clock: string;
  elapsed: string;
  tokensToday: string;
  jobTokens: string;
  hardenTokens: string;
  
  // Streamed Event Trace Buffer
  allEvents: TraceEvent[];

  // Actions
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
  tokensToday: '284K',
  jobTokens: '44.1k',
  hardenTokens: '13.7k',
  allEvents: [],

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
    set((state) => ({
      allEvents: [event, ...state.allEvents].slice(0, 100)
    })),

  tickClock: () => {
    const state = get();
    const nextTick = state.tick + 1;
    const elapsedS = 521 + nextTick;
    const elapsed = `${pad(Math.floor(elapsedS / 60), 2)}:${pad(elapsedS % 60, 2)}`;
    const clockS = baseTs + nextTick;
    const clock = `${pad(Math.floor(clockS / 3600), 2)}:${pad(Math.floor(clockS / 60) % 60, 2)}`;
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
  }
}));

// Background client-only clock ticker
if (typeof window !== 'undefined') {
  setInterval(() => {
    useConsoleStore.getState().tickClock();
  }, 1000);
}
