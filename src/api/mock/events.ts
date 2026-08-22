export const RAW_SEED_EVENTS = [
  { a: 'hermes', k: 'job.start', d: '#142 moveinmate/backend feat/redis-state', dur: '', t: 0 },
  { a: 'gemini', k: 'agent.start', d: 'BUILD · antigravity-2.5-pro', dur: '', t: 0.4 },
  { a: 'gemini', k: 'tool.start', d: 'read_file src/state/store.py', dur: '', t: 1.1 },
  { a: 'gemini', k: 'tool.end', d: 'read_file src/state/store.py', dur: '571 ms', t: 1.7 },
  { a: 'gemini', k: 'tool.start', d: 'write_file src/state/redis_store.py', dur: '', t: 3.0 },
  { a: 'gemini', k: 'tool.end', d: 'write_file src/state/redis_store.py', dur: '1.22 s', t: 4.2 },
  { a: 'gemini', k: 'tool.start', d: 'run pytest tests/state/ -q', dur: '', t: 5.0 },
  { a: 'gemini', k: 'error', d: 'redis connection refused (sandbox)', dur: '', t: 6.4 },
  { a: 'hermes', k: 'retry', d: 'attempt 2 · local container', dur: '', t: 6.9 },
  { a: 'gemini', k: 'tool.end', d: '184 passed · 2 skipped', dur: '18.4 s', t: 25.3 },
  { a: 'hermes', k: 'budget.check', d: 'BUILD closed at 30.4k tokens', dur: '4 ms', t: 26.0 },
  { a: 'hermes', k: 'phase.change', d: 'BUILD → HARDEN', dur: '', t: 27.6 },
  { a: 'claude', k: 'agent.start', d: 'HARDEN · claude-sonnet-4-5', dur: '', t: 27.9 },
  { a: 'claude', k: 'tool.start', d: 'read_file src/state/redis_store.py', dur: '', t: 28.5 },
  { a: 'claude', k: 'tool.end', d: 'read_file src/state/redis_store.py', dur: '708 ms', t: 29.2 },
  { a: 'hermes', k: 'quota.warn', d: 'Codex weekly allowance at 78% (estimated)', dur: '', t: 30.1 },
  { a: 'claude', k: 'agent.note', d: 'race: read-after-write on flush()', dur: '', t: 31.4 }
];

export const RAW_POOL_EVENTS = [
  { a: 'claude', k: 'tool.start', d: 'read_file src/state/redis_store.py', dur: '' },
  { a: 'claude', k: 'tool.end', d: 'read_file src/state/redis_store.py', dur: '612 ms' },
  { a: 'gemini', k: 'tool.start', d: 'write_file src/state/redis_store.py', dur: '' },
  { a: 'gemini', k: 'tool.end', d: 'write_file src/state/redis_store.py', dur: '1.24 s' },
  { a: 'gemini', k: 'tool.start', d: 'run pytest tests/state/ -q', dur: '' },
  { a: 'gemini', k: 'tool.end', d: '184 passed · 2 skipped', dur: '18.4 s' },
  { a: 'claude', k: 'agent.note', d: 'race: read-after-write on flush()', dur: '' },
  { a: 'hermes', k: 'budget.check', d: 'job #142 44.1k / 80k · ok', dur: '3 ms' },
  { a: 'claude', k: 'tool.start', d: 'write_file docs/adr/0007-state.md', dur: '' },
  { a: 'claude', k: 'tool.end', d: 'write_file docs/adr/0007-state.md', dur: '844 ms' },
  { a: 'herdr', k: 'runtime.probe', d: 'redis://localhost:6379 pong', dur: '2 ms' },
  { a: 'hermes', k: 'queue.peek', d: 'next #143 unigreen/web · P0', dur: '1 ms' },
  { a: 'codex', k: 'agent.wait', d: 'awaiting HARDEN handoff', dur: '' },
  { a: 'gemini', k: 'tool.start', d: 'read_file src/state/store.py', dur: '' },
  { a: 'gemini', k: 'tool.end', d: 'read_file src/state/store.py', dur: '389 ms' },
  { a: 'hermes', k: 'phase.change', d: 'BUILD → HARDEN', dur: '' }
];
