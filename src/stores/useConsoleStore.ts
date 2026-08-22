import { create } from 'zustand';
import { TraceEvent } from '../api/types';
import { RAW_SEED_EVENTS, RAW_POOL_EVENTS } from '../api/mock/events';
import { resolveActorRef } from '../api/mock/actors';

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
  qFilter: string;
  eFilter: string;
  liveMotion: boolean;
  ambient3d: boolean;
  portraits: 'both' | 'slots' | 'marks';
  
  // Real-time Clock & Simulation State
  tick: number;
  lastTs: number;
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
  setQFilter: (filter: string) => void;
  setEFilter: (filter: string) => void;
  setLiveMotion: (enabled: boolean) => void;
  setAmbient3d: (enabled: boolean) => void;
  setPortraits: (mode: 'both' | 'slots' | 'marks') => void;
  addTraceEvent: (event: TraceEvent) => void;
  tickClock: () => void;
}

const baseTs = 10 * 3600 + 42 * 60 + 16;
const initialEvents: TraceEvent[] = RAW_SEED_EVENTS.map((e, idx) => ({
  id: `seed-${idx}`,
  ts: fmtTs(baseTs + e.t),
  rawTs: baseTs + e.t,
  source: resolveActorRef(e.a),
  kind: e.k,
  detail: e.d,
  dur: e.dur || '—',
  jobId: '#142'
})).reverse();

export const useConsoleStore = create<ConsoleUIState>((set, get) => ({
  selectedAgentId: 'claude',
  activeModalJobId: null,
  qFilter: 'All',
  eFilter: 'All',
  liveMotion: true,
  ambient3d: true,
  portraits: 'both',
  
  tick: 0,
  lastTs: baseTs + 31.4,
  clock: '10:42',
  elapsed: '08:41',
  tokensToday: '284K',
  jobTokens: '44.1k',
  hardenTokens: '13.7k',
  allEvents: initialEvents,

  setSelectedAgentId: (id) => set({ selectedAgentId: id.toLowerCase() }),
  setActiveModalJobId: (id) => set({ activeModalJobId: id }),
  setQFilter: (qFilter) => set({ qFilter }),
  setEFilter: (eFilter) => set({ eFilter }),
  setLiveMotion: (liveMotion) => set({ liveMotion }),
  setAmbient3d: (ambient3d) => set({ ambient3d }),
  setPortraits: (portraits) => set({ portraits }),

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

    let nextEvents = state.allEvents;
    let nextLastTs = state.lastTs;

    if (state.liveMotion && nextTick % 2 === 1) {
      const p = RAW_POOL_EVENTS[Math.floor(nextTick / 2) % RAW_POOL_EVENTS.length];
      const ts = state.lastTs + 0.4 + ((nextTick * 37) % 130) / 100;
      const newEvent: TraceEvent = {
        id: `evt-${nextTick}-${Date.now()}`,
        ts: fmtTs(ts),
        rawTs: ts,
        source: resolveActorRef(p.a),
        kind: p.k,
        detail: p.d,
        dur: p.dur || '—',
        jobId: '#142'
      };
      nextEvents = [newEvent, ...state.allEvents].slice(0, 100);
      nextLastTs = ts;
    }

    set({
      tick: nextTick,
      lastTs: nextLastTs,
      clock,
      elapsed,
      jobTokens,
      hardenTokens,
      tokensToday,
      allEvents: nextEvents
    });
  }
}));

// Background live pulse ticker
if (typeof window !== 'undefined') {
  setInterval(() => {
    useConsoleStore.getState().tickClock();
  }, 1000);
}
