import { AgentData, JobItem, PipelineStep, ProviderQuota, ProjectionItem, SettingItem, ChangedFile } from './types';

export const COLORS = {
  gem: '#5B8CFF',
  cla: '#D9A05B',
  cod: '#4EC9A0',
  ely: '#CBA35C',
  red: '#F2555A',
  amber: '#E3A008',
  green: '#3FB950',
  text: '#E6E9ED',
  dim: '#8C949F',
  faint: '#5C646E',
  line: '#1F242B'
};

export const AGENT_COLOR_MAP: Record<string, string> = {
  Gemini: COLORS.gem,
  Claude: COLORS.cla,
  Codex: COLORS.cod,
  Elysia: COLORS.ely,
  Hermes: '#CBA35C',
  LysControl: '#CBA35C',
  LysStack: '#CBA35C',
  Herdr: '#8C949F'
};

export const AGENTS_MAP: Record<string, AgentData> = {
  Gemini: {
    id: 'gemini',
    name: 'Gemini',
    model: 'antigravity-2.5-pro',
    provider: 'Google AI Studio',
    role: 'Implementation · scaffolding · migrations',
    status: 'RUNNING',
    phase: 'BUILD',
    task: 'Implementing RedisVehicleStateStore and wiring the migration path off the in-memory store.',
    tool: 'tool: pytest',
    color: COLORS.gem,
    ctxUsed: '68.1k',
    ctxMax: '200k',
    ctxPct: '34%',
    input: '44.8k',
    output: '17.9k',
    cached: '5.4k',
    remaining: '131.9k',
    inPct: '22%',
    outPct: '9%',
    cachePct: '3%',
    avatarUrl: '/agents/gemini.webp',
    crawlCode: 'redis.connect()\nSET vehicle:1042\npipeline.exec\nasync def flush\nawait store.put\nTTL 900\nkeys scanned 84\nmigrate batch 3\n',
    frameLog: 'redis.connect() ok\nstate_store.write batch 3',
    traceId: 'trc 9f14·build',
    depth: 2,
    capacity: '≈ 4–6 medium jobs',
    reset: 'daily 00:00 UTC',
    resetNote: 'Request quota is reported by AI Studio. Job capacity is inferred from a 27.4k median BUILD run — a range, not a count.',
    allowance: [
      { label: 'session', value: '68.1k', pct: '34%', tag: 'EXACT' },
      { label: 'daily requests', value: '834 / 1500', pct: '56%', tag: 'EXACT' },
      { label: 'weekly', value: 'not metered', pct: '0%', tag: 'N/A' }
    ],
    activity: [
      { op: 'READ', path: 'src/state/store.py', meta: '1.2k tok' },
      { op: 'WRITE', path: 'src/state/redis_store.py', meta: '+184 −12' },
      { op: 'RUN', path: 'pytest tests/state/ -q', meta: '18.4s' },
      { op: 'READ', path: 'docs/adr/0007-state.md', meta: '0.8k tok' }
    ],
    metrics: [
      { label: 'JOBS COMPLETED', value: '126', sub: 'last 30d' },
      { label: 'AVG TOKENS/JOB', value: '27.4k', sub: 'σ 9.1k' },
      { label: 'MEDIAN DURATION', value: '6m 12s', sub: 'BUILD phase' },
      { label: 'P75 DURATION', value: '11m 04s', sub: '' },
      { label: 'SUCCESS RATE', value: '94.1%', sub: '118 / 126', color: COLORS.green },
      { label: 'RETRIES', value: '11', sub: '8.7% of runs' },
      { label: 'FAILURES', value: '7', sub: '5 sandbox, 2 syntax', color: COLORS.amber }
    ],
    runs: [
      { id: '#142', phase: 'BUILD', task: 'Move VehicleStateStore to Redis', tokens: '30.4k', dur: '08:41', result: 'RUNNING' },
      { id: '#139', phase: 'BUILD', task: 'Queue scheduler tests scaffold', tokens: '21.7k', dur: '05:18', result: 'PASSED' },
      { id: '#137', phase: 'BUILD', task: 'Auth refactor — session adapter', tokens: '34.2k', dur: '12:06', result: 'PASSED' },
      { id: '#134', phase: 'BUILD', task: 'Frontend a11y audit fixes', tokens: '18.9k', dur: '04:52', result: 'PASSED' },
      { id: '#131', phase: 'BUILD', task: 'CI cache layer for pytest', tokens: '26.1k', dur: '07:33', result: 'RETRIED' }
    ]
  },
  Claude: {
    id: 'claude',
    name: 'Claude',
    model: 'claude-sonnet-4-5',
    provider: 'Anthropic API',
    role: 'Architecture · review · hardening · docs',
    status: 'RUNNING',
    phase: 'HARDEN',
    task: 'Reviewing the store contract for TTL and read-after-write races before verification.',
    tool: 'tool: read_file',
    color: COLORS.cla,
    ctxUsed: '91.3k',
    ctxMax: '200k',
    ctxPct: '46%',
    input: '63.2k',
    output: '21.7k',
    cached: '6.4k',
    remaining: '108.7k',
    inPct: '31%',
    outPct: '11%',
    cachePct: '3%',
    avatarUrl: '/agents/claude.webp',
    crawlCode: 'review store.py\ninvariant: ttl>0\nrace: read/write\nnote: add lock\nfn signature ok\nsuggest retry\ndoc: state model\ncontract check\n',
    frameLog: 'read redis_store.py 2.9k\nnote race: read-after-write',
    traceId: 'trc 9f14·harden',
    depth: 1,
    capacity: '≈ 2–3 medium jobs',
    reset: '13:20 (2h 14m)',
    resetNote: 'The 5-hour window is reported exactly by the API. Weekly allowance and job capacity are inferred from recent run medians.',
    allowance: [
      { label: 'session', value: '91.3k', pct: '46%', tag: 'EXACT' },
      { label: '5h window', value: '41%', pct: '41%', tag: 'EXACT' },
      { label: 'weekly', value: '≈ 63%', pct: '63%', tag: 'EST' }
    ],
    activity: [
      { op: 'READ', path: 'src/state/redis_store.py', meta: '2.9k tok' },
      { op: 'READ', path: 'src/state/store.py', meta: '1.2k tok' },
      { op: 'WRITE', path: 'docs/adr/0007-state.md', meta: '+61 −4' },
      { op: 'NOTE', path: 'race: read-after-write on flush()', meta: 'blocking' }
    ],
    metrics: [
      { label: 'JOBS COMPLETED', value: '98', sub: 'last 30d' },
      { label: 'AVG TOKENS/JOB', value: '41.6k', sub: 'σ 14.2k' },
      { label: 'MEDIAN DURATION', value: '4m 38s', sub: 'HARDEN phase' },
      { label: 'P75 DURATION', value: '8m 21s', sub: '' },
      { label: 'SUCCESS RATE', value: '97.9%', sub: '96 / 98', color: COLORS.green },
      { label: 'RETRIES', value: '3', sub: '3.1% of runs' },
      { label: 'FAILURES', value: '2', sub: 'both context overflow', color: COLORS.amber }
    ],
    runs: [
      { id: '#142', phase: 'HARDEN', task: 'Move VehicleStateStore to Redis', tokens: '13.7k', dur: '02:14', result: 'RUNNING' },
      { id: '#140', phase: 'HARDEN', task: 'CI regression fix — flaky worker', tokens: '38.4k', dur: '05:02', result: 'PASSED' },
      { id: '#137', phase: 'HARDEN', task: 'Auth refactor — session adapter', tokens: '52.8k', dur: '09:47', result: 'PASSED' },
      { id: '#136', phase: 'HARDEN', task: 'Hermes phase policy rewrite', tokens: '44.1k', dur: '07:18', result: 'PASSED' },
      { id: '#133', phase: 'HARDEN', task: 'Memory compaction review', tokens: '29.6k', dur: '03:51', result: 'PASSED' }
    ]
  },
  Codex: {
    id: 'codex',
    name: 'Codex',
    model: 'gpt-5-codex',
    provider: 'OpenAI (plan quota)',
    role: 'Verification · tests · static analysis · regressions',
    status: 'WAITING',
    phase: 'VERIFY',
    task: 'Waiting on HARDEN to release the branch. Verification plan staged: 186 tests, mypy strict, ruff.',
    tool: 'tool: —',
    color: COLORS.cod,
    ctxUsed: '16.2k',
    ctxMax: '200k',
    ctxPct: '8%',
    input: '14.1k',
    output: '1.4k',
    cached: '0.7k',
    remaining: '183.8k',
    inPct: '7%',
    outPct: '1%',
    cachePct: '1%',
    avatarUrl: '/agents/codex.webp',
    crawlCode: 'pytest -q\ncollect 186\nassert eq 200\nmypy strict\nruff --fix\ncov 91.4%\nregress none\nsnapshot diff\n',
    frameLog: 'stage pytest -q · 186\nawait HARDEN handoff',
    traceId: 'trc 9f14·verify',
    depth: 3,
    capacity: '≈ 1–2 substantial runs',
    reset: '≈ Sun 00:00 (est)',
    resetNote: 'OpenAI exposes no plan counter. Both the weekly figure and the reset time are estimated from 7 recent runs at a 18.4k median.',
    allowance: [
      { label: 'session', value: '16.2k', pct: '8%', tag: 'EXACT' },
      { label: 'weekly plan', value: '≈ 78%', pct: '78%', tag: 'EST' },
      { label: 'daily', value: 'no counter', pct: '0%', tag: 'N/A' }
    ],
    activity: [
      { op: 'STAGE', path: 'pytest tests/ -q --maxfail=1', meta: 'queued' },
      { op: 'STAGE', path: 'mypy --strict src/state', meta: 'queued' },
      { op: 'STAGE', path: 'ruff check src tests', meta: 'queued' },
      { op: 'IDLE', path: 'awaiting HARDEN handoff', meta: '02:14' }
    ],
    metrics: [
      { label: 'JOBS COMPLETED', value: '104', sub: 'last 30d' },
      { label: 'AVG TOKENS/JOB', value: '18.4k', sub: 'σ 6.0k' },
      { label: 'MEDIAN DURATION', value: '3m 21s', sub: 'VERIFY phase' },
      { label: 'P75 DURATION', value: '5m 44s', sub: '' },
      { label: 'SUCCESS RATE', value: '91.3%', sub: '95 / 104', color: COLORS.amber },
      { label: 'RETRIES', value: '14', sub: '13.5% of runs' },
      { label: 'FAILURES', value: '9', sub: '6 rate limited', color: COLORS.red }
    ],
    runs: [
      { id: '#141', phase: 'VERIFY', task: 'Frontend accessibility audit', tokens: '16.8k', dur: '03:02', result: 'PASSED' },
      { id: '#140', phase: 'VERIFY', task: 'CI regression fix — flaky worker', tokens: '22.4k', dur: '04:36', result: 'PASSED' },
      { id: '#138', phase: 'VERIFY', task: 'Queue scheduler tests', tokens: '19.1k', dur: '03:44', result: 'FAILED' },
      { id: '#137', phase: 'VERIFY', task: 'Auth refactor — session adapter', tokens: '24.6k', dur: '05:11', result: 'RATE LIMITED' },
      { id: '#135', phase: 'VERIFY', task: 'Redis client compat matrix', tokens: '12.2k', dur: '02:18', result: 'PASSED' }
    ]
  },
  Elysia: {
    id: 'elysia',
    name: 'Elysia',
    model: 'lys-tactical-orchestrator-v1',
    provider: 'LysControl Core',
    role: 'Autonomous synthesis · tactical arbitration · dispatch',
    status: 'RUNNING',
    phase: 'COMPLETE',
    task: 'Overseeing agent handoffs, budget convergence, and state machine integrity.',
    tool: 'tool: dispatch',
    color: COLORS.ely,
    ctxUsed: '42.8k',
    ctxMax: '200k',
    ctxPct: '21%',
    input: '31.2k',
    output: '8.4k',
    cached: '3.2k',
    remaining: '157.2k',
    inPct: '15%',
    outPct: '4%',
    cachePct: '2%',
    avatarUrl: '/agents/elysia.webp',
    crawlCode: 'mesh.sync()\npolicy.assert(budget<cap)\nqueue.prioritize(P0)\nhandoff.verify()\nmetrics.emit()\n',
    frameLog: 'orchestrator active\nconsensus 4/4 nodes',
    traceId: 'trc 9f14·dispatch',
    depth: 0,
    capacity: 'unlimited local',
    reset: 'continuous',
    resetNote: 'Local orchestration controller. Operates with zero API rate limits.',
    allowance: [
      { label: 'session', value: '42.8k', pct: '21%', tag: 'EXACT' },
      { label: 'routing quota', value: '100%', pct: '100%', tag: 'EXACT' },
      { label: 'network', value: 'unmetered', pct: '0%', tag: 'N/A' }
    ],
    activity: [
      { op: 'READ', path: 'config/policy.toml', meta: '0.4k tok' },
      { op: 'RUN', path: 'mesh.broadcast_status()', meta: '1.4ms' },
      { op: 'NOTE', path: 'pipeline handoff scheduled', meta: '04:00' }
    ],
    metrics: [
      { label: 'JOBS ORCHESTRATED', value: '342', sub: 'all-time' },
      { label: 'HANDOFF EFFICIENCY', value: '99.4%', sub: 'sub-second' },
      { label: 'BUDGET DRIFT', value: '±1.2%', sub: 'optimal' },
      { label: 'SYSTEM HEALTH', value: '100%', sub: '4/4 daemons', color: COLORS.green }
    ],
    runs: [
      { id: '#142', phase: 'COMPLETE', task: 'Redis State Migration Orchestration', tokens: '8.4k', dur: '10:38', result: 'RUNNING' },
      { id: '#141', phase: 'COMPLETE', task: 'Frontend A11y Audit Chain', tokens: '4.2k', dur: '09:12', result: 'PASSED' }
    ]
  }
};

export const INITIAL_QUEUE: JobItem[] = [
  { prio: 'P0', id: '#143', task: 'Fix production CI — flaky worker teardown', repo: 'unigreen/web', chain: ['Gemini', 'Claude', 'Codex'], tokens: '~18–30k', time: '~12 min', status: 'QUEUED' },
  { prio: 'P1', id: '#144', task: 'Authentication refactor — session adapter', repo: 'moveinmate/backend', chain: ['Gemini', 'Claude'], tokens: '~40–55k', time: '~21 min', status: 'BLOCKED' },
  { prio: 'P1', id: '#145', task: 'Queue scheduler regression tests', repo: 'hermes-lab', chain: ['Codex'], tokens: '~22k', time: '~7 min', status: 'QUEUED' },
  { prio: 'P2', id: '#146', task: 'Frontend accessibility audit pass 2', repo: 'unigreen/web', chain: ['Gemini', 'Codex'], tokens: '~14k', time: '~6 min', status: 'QUEUED' },
  { prio: 'P2', id: '#147', task: 'Memory compaction policy rewrite', repo: 'lyscontrol/core', chain: ['Claude', 'Codex'], tokens: '~27k', time: '~14 min', status: 'QUEUED' },
  { prio: 'P3', id: '#148', task: 'Redis client compatibility matrix', repo: 'moveinmate/backend', chain: ['Gemini', 'Claude', 'Codex'], tokens: '~16–34k', time: '~18 min', status: 'QUEUED' },
  { prio: 'P1', id: '#141', task: 'Frontend accessibility audit', repo: 'unigreen/web', chain: ['Gemini', 'Codex'], tokens: '34.9k', time: '09:12', status: 'COMPLETED' },
  { prio: 'P2', id: '#136', task: 'Hermes phase policy rewrite', repo: 'hermes-lab', chain: ['Claude'], tokens: '44.1k', time: '07:18', status: 'CANCELLED' }
];

export const INITIAL_PIPELINE: PipelineStep[] = [
  { id: '#142', phase: 'BUILD', agent: 'Gemini', task: 'Move VehicleStateStore to Redis', meta: '30.4k · 06:12', state: 'COMPLETE', note: 'implementation complete' },
  { id: '#142', phase: 'HARDEN', agent: 'Claude', task: 'Review store contract — TTL, read-after-write', meta: '02:14', state: 'RUNNING', note: 'reviewing store contract' },
  { id: '#142', phase: 'VERIFY', agent: 'Codex', task: '186 tests · mypy strict · ruff', meta: 'staged ~19k', state: 'QUEUED', note: 'waiting for handoff' },
  { id: '#143', phase: 'BUILD', agent: 'Gemini', task: 'Fix production CI — flaky worker teardown', meta: '~18–30k', state: 'CLAIMED' },
  { id: '#144', phase: 'BUILD', agent: 'Gemini', task: 'Authentication refactor — session adapter', meta: 'waiting on repo lock', state: 'BLOCKED' }
];

export const ACTIVE_JOB_CHANGED_FILES: ChangedFile[] = [
  { mark: 'A', path: 'src/state/redis_store.py', add: '+184', del: '−0', by: 'Gemini' },
  { mark: 'M', path: 'src/state/store.py', add: '+22', del: '−96', by: 'Gemini' },
  { mark: 'M', path: 'src/state/__init__.py', add: '+4', del: '−2', by: 'Gemini' },
  { mark: 'A', path: 'tests/state/test_redis_store.py', add: '+141', del: '−0', by: 'Gemini' },
  { mark: 'M', path: 'tests/state/test_migration.py', add: '+38', del: '−11', by: 'Gemini' },
  { mark: 'M', path: 'docs/adr/0007-state.md', add: '+61', del: '−4', by: 'Claude' },
  { mark: 'M', path: 'compose.yaml', add: '+9', del: '−0', by: 'Gemini' }
];

export const PROVIDER_QUOTAS: ProviderQuota[] = [
  {
    name: 'CLAUDE',
    color: COLORS.cla,
    pct: '41%',
    tag: 'EXACT',
    window: '5-hour rolling window',
    left: '59% remaining · resets 13:20',
    capacity: '≈ 2–3 medium jobs',
    reset: '2h 14m',
    resetTag: 'EXACT',
    conf: 'api reported',
    basis: 'Reported directly by the Anthropic API\nrate-limit headers on every response.',
    opacity: '0.9'
  },
  {
    name: 'CODEX',
    color: COLORS.cod,
    pct: '78%',
    tag: 'ESTIMATED',
    window: 'Weekly plan allowance',
    left: 'likely 1–2 substantial runs',
    capacity: '≈ 1–2 substantial runs',
    reset: '≈ Sun 00:00',
    resetTag: 'EST',
    conf: 'confidence low',
    basis: 'Estimate based on:\n7 recent Codex runs\nmedian 18.4k tokens/run\nNo provider counter exposed.',
    opacity: '0.55'
  },
  {
    name: 'ANTIGRAVITY / GEMINI',
    color: COLORS.gem,
    pct: '56%',
    tag: 'EXACT',
    window: 'Daily request quota',
    left: '834 / 1500 requests used',
    capacity: '≈ 4–6 medium jobs',
    reset: '00:00 UTC',
    resetTag: 'EXACT',
    conf: 'api reported',
    basis: 'Counted from AI Studio request ledger.\nToken ceiling not enforced on this key.',
    opacity: '0.9'
  },
  {
    name: 'HERDR LOCAL RUNTIME',
    color: '#8C949F',
    pct: '0%',
    tag: 'UNKNOWN',
    window: 'No metering',
    left: 'unmetered',
    capacity: 'bounded by wall clock',
    reset: '—',
    resetTag: 'N/A',
    conf: 'not tracked',
    basis: 'Local execution. No quota to report;\nbounded only by wall-clock and CPU.',
    opacity: '0.3'
  }
];

export const PROJECTIONS: ProjectionItem[] = [
  { id: '#145', task: 'Queue scheduler regression tests', est: '~22k', w: '24%', wLow: '18%', color: COLORS.cod, conf: 'medium' },
  { id: '#146', task: 'Frontend accessibility audit', est: '~14k', w: '15%', wLow: '12%', color: COLORS.gem, conf: 'high' },
  { id: '#147', task: 'Memory compaction policy', est: '~27k', w: '30%', wLow: '21%', color: COLORS.cla, conf: 'medium' },
  { id: '#148', task: 'Redis client compat matrix', est: '~16–34k', w: '37%', wLow: '18%', color: COLORS.amber, conf: 'low' }
];

export const SET_RUNTIME_DATA: SettingItem[] = [
  { label: 'hermes orchestrator', value: 'running · pid 4188', color: COLORS.green },
  { label: 'herdr sandbox', value: 'local container', color: '#E6E9ED' },
  { label: 'state store', value: 'redis://localhost:6379', color: '#E6E9ED' },
  { label: 'trace retention', value: '14 days', color: '#E6E9ED' },
  { label: 'reduced motion', value: 'follow system', color: '#8C949F' }
];

export const SET_POLICY_DATA: SettingItem[] = [
  { label: 'sprint budget', value: '300k tokens', color: '#E6E9ED' },
  { label: 'per-job cap', value: '80k tokens', color: '#E6E9ED' },
  { label: 'hard stop', value: 'pause at 246k', color: COLORS.red },
  { label: 'retries per phase', value: '3', color: '#E6E9ED' },
  { label: 'concurrency policy', value: 'serial per repository', color: '#E6E9ED' }
];

export const SEED_EVENTS = [
  { a: 'Hermes', k: 'job.start', d: '#142 moveinmate/backend feat/redis-state', dur: '', t: 0 },
  { a: 'Gemini', k: 'agent.start', d: 'BUILD · antigravity-2.5-pro', dur: '', t: 0.4 },
  { a: 'Gemini', k: 'tool.start', d: 'read_file src/state/store.py', dur: '', t: 1.1 },
  { a: 'Gemini', k: 'tool.end', d: 'read_file src/state/store.py', dur: '571 ms', t: 1.7 },
  { a: 'Gemini', k: 'tool.start', d: 'write_file src/state/redis_store.py', dur: '', t: 3.0 },
  { a: 'Gemini', k: 'tool.end', d: 'write_file src/state/redis_store.py', dur: '1.22 s', t: 4.2 },
  { a: 'Gemini', k: 'tool.start', d: 'run pytest tests/state/ -q', dur: '', t: 5.0 },
  { a: 'Gemini', k: 'error', d: 'redis connection refused (sandbox)', dur: '', t: 6.4 },
  { a: 'Hermes', k: 'retry', d: 'attempt 2 · local container', dur: '', t: 6.9 },
  { a: 'Gemini', k: 'tool.end', d: '184 passed · 2 skipped', dur: '18.4 s', t: 25.3 },
  { a: 'Hermes', k: 'budget.check', d: 'BUILD closed at 30.4k tokens', dur: '4 ms', t: 26.0 },
  { a: 'Hermes', k: 'phase.change', d: 'BUILD → HARDEN', dur: '', t: 27.6 },
  { a: 'Claude', k: 'agent.start', d: 'HARDEN · claude-sonnet-4-5', dur: '', t: 27.9 },
  { a: 'Claude', k: 'tool.start', d: 'read_file src/state/redis_store.py', dur: '', t: 28.5 },
  { a: 'Claude', k: 'tool.end', d: 'read_file src/state/redis_store.py', dur: '708 ms', t: 29.2 },
  { a: 'Hermes', k: 'quota.warn', d: 'Codex weekly allowance at 78% (estimated)', dur: '', t: 30.1 },
  { a: 'Claude', k: 'agent.note', d: 'race: read-after-write on flush()', dur: '', t: 31.4 }
];

export const POOL_EVENTS = [
  { a: 'Claude', k: 'tool.start', d: 'read_file src/state/redis_store.py', dur: '' },
  { a: 'Claude', k: 'tool.end', d: 'read_file src/state/redis_store.py', dur: '612 ms' },
  { a: 'Gemini', k: 'tool.start', d: 'write_file src/state/redis_store.py', dur: '' },
  { a: 'Gemini', k: 'tool.end', d: 'write_file src/state/redis_store.py', dur: '1.24 s' },
  { a: 'Gemini', k: 'tool.start', d: 'run pytest tests/state/ -q', dur: '' },
  { a: 'Gemini', k: 'tool.end', d: '184 passed · 2 skipped', dur: '18.4 s' },
  { a: 'Claude', k: 'agent.note', d: 'race: read-after-write on flush()', dur: '' },
  { a: 'Hermes', k: 'budget.check', d: 'job #142 44.1k / 80k · ok', dur: '3 ms' },
  { a: 'Claude', k: 'tool.start', d: 'write_file docs/adr/0007-state.md', dur: '' },
  { a: 'Claude', k: 'tool.end', d: 'write_file docs/adr/0007-state.md', dur: '844 ms' },
  { a: 'Herdr', k: 'runtime.probe', d: 'redis://localhost:6379 pong', dur: '2 ms' },
  { a: 'Hermes', k: 'queue.peek', d: 'next #143 unigreen/web · P0', dur: '1 ms' },
  { a: 'Codex', k: 'agent.wait', d: 'awaiting HARDEN handoff', dur: '' },
  { a: 'Gemini', k: 'tool.start', d: 'read_file src/state/store.py', dur: '' },
  { a: 'Gemini', k: 'tool.end', d: 'read_file src/state/store.py', dur: '389 ms' },
  { a: 'Hermes', k: 'phase.change', d: 'BUILD → HARDEN', dur: '' }
];
