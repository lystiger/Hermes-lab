import { AgentDetail, AgentId } from '../types';

export const MOCK_AGENTS: Record<AgentId, AgentDetail> = {
  gemini: {
    id: 'gemini',
    displayName: 'Gemini',
    provider: 'Google AI Studio',
    model: 'antigravity-2.5-pro',
    role: 'Implementation · scaffolding · migrations',
    capabilities: ['build', 'scaffolding', 'migrations', 'refactoring'],
    status: 'RUNNING',
    phase: 'BUILD',
    currentTask: 'Implementing RedisVehicleStateStore and wiring the migration path off the in-memory store.',
    activeTool: 'tool: pytest',
    contextPct: '34%',
    contextUsed: '68.1k',
    contextMax: '200k',
    queueDepth: 2,
    sessionTokens: '30.4k',
    presentation: {
      displayName: 'Gemini',
      avatarUrl: '/agents/gemini.webp',
      characterCardUrl: '/agents/gemini-card.webp',
      accentColor: 'var(--lys-agent-gemini)',
      animationProfile: 'quick',
      sigil: 'BUILD',
      code: 'G-01',
      badge: 'BUILD'
    },
    input: '44.8k',
    output: '17.9k',
    cached: '5.4k',
    remaining: '131.9k',
    inPct: '22%',
    outPct: '9%',
    cachePct: '3%',
    crawlCode: 'redis.connect()\nSET vehicle:1042\npipeline.exec\nasync def flush\nawait store.put\nTTL 900\nkeys scanned 84\nmigrate batch 3\n',
    frameLog: 'redis.connect() ok\nstate_store.write batch 3',
    traceId: 'trc 9f14·build',
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
      { label: 'SUCCESS RATE', value: '94.1%', sub: '118 / 126', color: '#3FB950' },
      { label: 'RETRIES', value: '11', sub: '8.7% of runs' },
      { label: 'FAILURES', value: '7', sub: '5 sandbox, 2 syntax', color: '#E3A008' }
    ],
    runs: [
      { id: '#142', phase: 'BUILD', task: 'Move VehicleStateStore to Redis', tokens: '30.4k', dur: '08:41', result: 'RUNNING' },
      { id: '#139', phase: 'BUILD', task: 'Queue scheduler tests scaffold', tokens: '21.7k', dur: '05:18', result: 'PASSED' },
      { id: '#137', phase: 'BUILD', task: 'Auth refactor — session adapter', tokens: '34.2k', dur: '12:06', result: 'PASSED' },
      { id: '#134', phase: 'BUILD', task: 'Frontend a11y audit fixes', tokens: '18.9k', dur: '04:52', result: 'PASSED' },
      { id: '#131', phase: 'BUILD', task: 'CI cache layer for pytest', tokens: '26.1k', dur: '07:33', result: 'RETRIED' }
    ]
  },
  claude: {
    id: 'claude',
    displayName: 'Claude',
    provider: 'Anthropic API',
    model: 'claude-sonnet-4-5',
    role: 'Architecture · review · hardening · docs',
    capabilities: ['architecture', 'security-review', 'hardening', 'documentation'],
    status: 'RUNNING',
    phase: 'HARDEN',
    currentTask: 'Reviewing the store contract for TTL and read-after-write races before verification.',
    activeTool: 'tool: read_file',
    contextPct: '46%',
    contextUsed: '91.3k',
    contextMax: '200k',
    queueDepth: 1,
    sessionTokens: '13.7k',
    presentation: {
      displayName: 'Claude',
      avatarUrl: '/agents/claude.webp',
      characterCardUrl: '/agents/claude-card.webp',
      accentColor: 'var(--lys-agent-claude)',
      animationProfile: 'relaxed',
      sigil: 'HARDEN',
      code: 'C-02',
      badge: 'HARDEN'
    },
    input: '63.2k',
    output: '21.7k',
    cached: '6.4k',
    remaining: '108.7k',
    inPct: '31%',
    outPct: '11%',
    cachePct: '3%',
    crawlCode: 'review store.py\ninvariant: ttl>0\nrace: read/write\nnote: add lock\nfn signature ok\nsuggest retry\ndoc: state model\ncontract check\n',
    frameLog: 'read redis_store.py 2.9k\nnote race: read-after-write',
    traceId: 'trc 9f14·harden',
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
      { label: 'SUCCESS RATE', value: '97.9%', sub: '96 / 98', color: '#3FB950' },
      { label: 'RETRIES', value: '3', sub: '3.1% of runs' },
      { label: 'FAILURES', value: '2', sub: 'both context overflow', color: '#E3A008' }
    ],
    runs: [
      { id: '#142', phase: 'HARDEN', task: 'Move VehicleStateStore to Redis', tokens: '13.7k', dur: '02:14', result: 'RUNNING' },
      { id: '#140', phase: 'HARDEN', task: 'CI regression fix — flaky worker', tokens: '38.4k', dur: '05:02', result: 'PASSED' },
      { id: '#137', phase: 'HARDEN', task: 'Auth refactor — session adapter', tokens: '52.8k', dur: '09:47', result: 'PASSED' },
      { id: '#136', phase: 'HARDEN', task: 'Hermes phase policy rewrite', tokens: '44.1k', dur: '07:18', result: 'PASSED' },
      { id: '#133', phase: 'HARDEN', task: 'Memory compaction review', tokens: '29.6k', dur: '03:51', result: 'PASSED' }
    ]
  },
  codex: {
    id: 'codex',
    displayName: 'Codex',
    provider: 'OpenAI (plan quota)',
    model: 'gpt-5-codex',
    role: 'Verification · tests · static analysis · regressions',
    capabilities: ['verification', 'unit-tests', 'static-analysis', 'regression-testing'],
    status: 'WAITING',
    phase: 'VERIFY',
    currentTask: 'Waiting on HARDEN to release the branch. Verification plan staged: 186 tests, mypy strict, ruff.',
    activeTool: 'tool: —',
    contextPct: '8%',
    contextUsed: '16.2k',
    contextMax: '200k',
    queueDepth: 3,
    sessionTokens: '0k',
    presentation: {
      displayName: 'Codex',
      avatarUrl: '/agents/codex.webp',
      characterCardUrl: '/agents/codex-card.webp',
      accentColor: 'var(--lys-agent-codex)',
      animationProfile: 'slow',
      sigil: 'VERIFY',
      code: 'X-03',
      badge: 'VERIFY'
    },
    input: '14.1k',
    output: '1.4k',
    cached: '0.7k',
    remaining: '183.8k',
    inPct: '7%',
    outPct: '1%',
    cachePct: '1%',
    crawlCode: 'pytest -q\ncollect 186\nassert eq 200\nmypy strict\nruff --fix\ncov 91.4%\nregress none\nsnapshot diff\n',
    frameLog: 'stage pytest -q · 186\nawait HARDEN handoff',
    traceId: 'trc 9f14·verify',
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
      { label: 'SUCCESS RATE', value: '91.3%', sub: '95 / 104', color: '#E3A008' },
      { label: 'RETRIES', value: '14', sub: '13.5% of runs' },
      { label: 'FAILURES', value: '9', sub: '6 rate limited', color: '#F2555A' }
    ],
    runs: [
      { id: '#141', phase: 'VERIFY', task: 'Frontend accessibility audit', tokens: '16.8k', dur: '03:02', result: 'PASSED' },
      { id: '#140', phase: 'VERIFY', task: 'CI regression fix — flaky worker', tokens: '22.4k', dur: '04:36', result: 'PASSED' },
      { id: '#138', phase: 'VERIFY', task: 'Queue scheduler tests', tokens: '19.1k', dur: '03:44', result: 'FAILED' },
      { id: '#137', phase: 'VERIFY', task: 'Auth refactor — session adapter', tokens: '24.6k', dur: '05:11', result: 'RATE LIMITED' },
      { id: '#135', phase: 'VERIFY', task: 'Redis client compat matrix', tokens: '12.2k', dur: '02:18', result: 'PASSED' }
    ]
  }
};

/**
 * Creates a generic agent object dynamically for unknown or newly registered models/subagents.
 */
export function createDynamicMockAgent(
  id: AgentId,
  displayName: string,
  provider: string,
  model: string,
  role: string,
  capabilities: string[] = ['general-execution']
): AgentDetail {
  return {
    id,
    displayName,
    provider,
    model,
    role,
    capabilities,
    status: 'IDLE',
    phase: 'REVIEW',
    currentTask: 'Awaiting task dispatch from Hermes scheduler.',
    activeTool: 'tool: —',
    contextPct: '5%',
    contextUsed: '10.0k',
    contextMax: '200k',
    queueDepth: 0,
    sessionTokens: '0k',
    presentation: {
      displayName,
      accentColor: '#8C949F',
      animationProfile: 'steady',
      sigil: 'AGENT',
      code: id.toUpperCase().slice(0, 4),
      badge: 'IDLE'
    },
    input: '8.0k',
    output: '2.0k',
    cached: '0k',
    remaining: '190.0k',
    inPct: '4%',
    outPct: '1%',
    cachePct: '0%',
    capacity: 'Standard tier capacity',
    reset: 'daily',
    resetNote: 'Standard dynamically registered agent quota.',
    allowance: [
      { label: 'session', value: '10.0k', pct: '5%', tag: 'EST' },
      { label: 'daily quota', value: 'unmetered', pct: '0%', tag: 'N/A' }
    ],
    activity: [
      { op: 'IDLE', path: 'ready for dispatch', meta: 'standby' }
    ],
    metrics: [
      { label: 'JOBS COMPLETED', value: '0', sub: 'new agent' },
      { label: 'AVG TOKENS/JOB', value: '—', sub: 'no data' },
      { label: 'SUCCESS RATE', value: '100%', sub: 'standby', color: '#3FB950' }
    ],
    runs: []
  };
}
