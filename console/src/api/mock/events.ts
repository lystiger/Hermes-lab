/** Mock trace events. Kinds and metadata follow what Hermes actually emits (see runner/run-hermes-sprint.py). */
export interface RawMockEvent {
  a: string;
  k: string;
  d: string;
  dur: string;
  t?: number;
  m?: Record<string, unknown>;
}

export const RAW_SEED_EVENTS: RawMockEvent[] = [
  { a: 'hermes', k: 'job.started', d: 'Sprint #142 execution started', dur: '', t: 0 },
  { a: 'gemini', k: 'phase.started', d: 'Starting phase build (builder) with agent gemini', dur: '', t: 0.4, m: { phase: 'build', role: 'builder', agent: 'gemini', order: 1 } },
  { a: 'gemini', k: 'tool.started', d: 'read_file src/state/store.py', dur: '', t: 1.1 },
  { a: 'gemini', k: 'tool.completed', d: 'read_file src/state/store.py', dur: '571 ms', t: 1.7 },
  { a: 'gemini', k: 'tool.started', d: 'write_file src/state/redis_store.py', dur: '', t: 3.0 },
  { a: 'gemini', k: 'tool.completed', d: 'write_file src/state/redis_store.py', dur: '1.22 s', t: 4.2 },
  { a: 'gemini', k: 'tool.started', d: 'run pytest tests/state/ -q', dur: '', t: 5.0 },
  { a: 'gemini', k: 'tool.failed', d: 'redis connection refused (sandbox)', dur: '', t: 6.4 },
  { a: 'gemini', k: 'tool.started', d: 'run pytest tests/state/ -q · local container', dur: '', t: 6.9 },
  { a: 'gemini', k: 'tool.completed', d: '184 passed · 2 skipped', dur: '18.4 s', t: 25.3 },
  { a: 'gemini', k: 'phase.completed', d: 'Phase build completed successfully', dur: '', t: 27.6, m: { phase: 'build', role: 'builder', agent: 'gemini', order: 1 } },
  { a: 'claude', k: 'phase.started', d: 'Starting phase harden (hardener) with agent claude', dur: '', t: 27.9, m: { phase: 'harden', role: 'hardener', agent: 'claude', order: 2 } },
  { a: 'claude', k: 'tool.started', d: 'read_file src/state/redis_store.py', dur: '', t: 28.5 },
  { a: 'claude', k: 'tool.completed', d: 'read_file src/state/redis_store.py', dur: '708 ms', t: 29.2 },
  { a: 'hermes', k: 'provider.rate_limited', d: 'Codex weekly allowance at 78% (estimated)', dur: '', t: 30.1 },
  { a: 'claude', k: 'message.created', d: 'race: read-after-write on flush()', dur: '', t: 31.4 }
];

/** Looping live events. No phase.* events here: those carry identity and are scripted in the seed. */
export const RAW_POOL_EVENTS: RawMockEvent[] = [
  { a: 'claude', k: 'tool.started', d: 'read_file src/state/redis_store.py', dur: '' },
  { a: 'claude', k: 'tool.completed', d: 'read_file src/state/redis_store.py', dur: '612 ms' },
  { a: 'claude', k: 'tool.started', d: 'write_file src/state/redis_store.py', dur: '' },
  { a: 'claude', k: 'tool.completed', d: 'write_file src/state/redis_store.py', dur: '1.24 s' },
  { a: 'claude', k: 'tool.started', d: 'run pytest tests/state/ -q', dur: '' },
  { a: 'claude', k: 'tool.completed', d: '184 passed · 2 skipped', dur: '18.4 s' },
  { a: 'claude', k: 'message.created', d: 'race: read-after-write on flush()', dur: '' },
  { a: 'hermes', k: 'model.call_completed', d: 'job #142 44.1k / 80k tokens', dur: '3 ms' },
  { a: 'claude', k: 'tool.started', d: 'write_file docs/adr/0007-state.md', dur: '' },
  { a: 'claude', k: 'tool.completed', d: 'write_file docs/adr/0007-state.md', dur: '844 ms' },
  { a: 'codex', k: 'agent.waiting', d: 'awaiting harden handoff', dur: '' }
];
