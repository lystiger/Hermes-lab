import { Job, JobDetail, JobPhase, ChangedFile } from '../types';

/** Start of the running mock job #142, so its elapsed time and phase times line up. */
const MOCK_ACTIVE_STARTED_AT = new Date(Date.now() - 14 * 60_000).toISOString();

export const MOCK_JOBS: Job[] = [
  {
    id: '#142',
    priority: 'P1',
    title: 'Redis State Migration',
    repository: 'moveinmate/backend',
    branch: 'feat/redis-state',
    assignedAgentIds: ['gemini', 'claude', 'codex'],
    status: 'RUNNING',
    currentPhase: 'build-store',
    createdAt: MOCK_ACTIVE_STARTED_AT,
    startedAt: MOCK_ACTIVE_STARTED_AT
  },
  {
    id: '#143',
    priority: 'P0',
    title: 'Fix production CI — flaky worker teardown',
    repository: 'unigreen/web',
    assignedAgentIds: ['gemini', 'claude', 'codex'],
    estimatedTokens: '~18–30k',
    estimatedTime: '~12 min',
    status: 'QUEUED',
    createdAt: '10:35'
  },
  {
    id: '#144',
    priority: 'P1',
    title: 'Authentication refactor — session adapter',
    repository: 'moveinmate/backend',
    assignedAgentIds: ['gemini', 'claude'],
    estimatedTokens: '~40–55k',
    estimatedTime: '~21 min',
    status: 'BLOCKED',
    createdAt: '10:30'
  },
  {
    id: '#145',
    priority: 'P1',
    title: 'Queue scheduler regression tests',
    repository: 'hermes-lab',
    assignedAgentIds: ['codex'],
    estimatedTokens: '~22k',
    estimatedTime: '~7 min',
    status: 'QUEUED',
    createdAt: '10:25'
  },
  {
    id: '#146',
    priority: 'P2',
    title: 'Frontend accessibility audit pass 2',
    repository: 'unigreen/web',
    assignedAgentIds: ['gemini', 'codex'],
    estimatedTokens: '~14k',
    estimatedTime: '~6 min',
    status: 'QUEUED',
    createdAt: '10:20'
  },
  {
    id: '#147',
    priority: 'P2',
    title: 'Memory compaction policy rewrite',
    repository: 'lyscontrol/core',
    assignedAgentIds: ['claude', 'codex'],
    estimatedTokens: '~27k',
    estimatedTime: '~14 min',
    status: 'QUEUED',
    createdAt: '10:15'
  },
  {
    id: '#148',
    priority: 'P3',
    title: 'Redis client compatibility matrix',
    repository: 'moveinmate/backend',
    assignedAgentIds: ['gemini', 'claude', 'codex'],
    estimatedTokens: '~16–34k',
    estimatedTime: '~18 min',
    status: 'QUEUED',
    createdAt: '10:10'
  },
  {
    id: '#141',
    priority: 'P1',
    title: 'Frontend accessibility audit',
    repository: 'unigreen/web',
    assignedAgentIds: ['gemini', 'codex'],
    estimatedTokens: '34.9k',
    estimatedTime: '09:12',
    status: 'COMPLETED',
    createdAt: '09:40',
    completedAt: '10:12'
  },
  {
    id: '#136',
    priority: 'P2',
    title: 'Hermes phase policy rewrite',
    repository: 'hermes-lab',
    assignedAgentIds: ['claude'],
    estimatedTokens: '44.1k',
    estimatedTime: '07:18',
    status: 'CANCELLED',
    createdAt: '09:15'
  }
];

export const MOCK_CHANGED_FILES: ChangedFile[] = [
  { mark: 'A', path: 'src/state/redis_store.py', add: '+184', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'src/state/store.py', add: '+22', del: '−96', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'src/state/__init__.py', add: '+4', del: '−2', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'A', path: 'tests/state/test_redis_store.py', add: '+141', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'tests/state/test_migration.py', add: '+38', del: '−11', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'docs/adr/0007-state.md', add: '+61', del: '−4', byActorId: 'claude', byDisplayName: 'Claude' },
  { mark: 'M', path: 'compose.yaml', add: '+9', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' }
];

/**
 * Phases shaped like Hermes GET /jobs/{id}, matching the mock agents: Gemini and Claude run a parallel group,
 * Codex waits on the harden phase. Builder and hardener each appear twice. Times are relative to load.
 */
function mockActivePhases(): JobPhase[] {
  const at = (minutesAgo: number) => new Date(Date.now() - minutesAgo * 60_000).toISOString();
  return [
    { id: 'phase-1-scaffold', name: 'scaffold', order: 1, role: 'builder', agentId: 'codex', status: 'SUCCEEDED', startedAt: at(14), completedAt: at(9.5), commitSha: '4ea5e4d1' },
    { id: 'phase-2-build-store', name: 'build-store', order: 2, role: 'builder', agentId: 'gemini', status: 'RUNNING', startedAt: at(9.5) },
    { id: 'phase-3-review-contract', name: 'review-contract', order: 3, role: 'hardener', agentId: 'claude', status: 'RUNNING', startedAt: at(9.5) },
    { id: 'phase-4-harden', name: 'harden', order: 4, role: 'hardener', agentId: 'codex', status: 'PENDING' },
    { id: 'phase-5-verify', name: 'verify', order: 5, role: 'verifier', agentId: 'claude', status: 'PENDING' }
  ];
}

export const MOCK_ACTIVE_JOB_DETAIL: JobDetail = {
  id: '#142',
  priority: 'P1',
  title: 'Redis State Migration',
  repository: 'moveinmate/backend',
  branch: 'feat/redis-state',
  status: 'RUNNING',
  currentPhase: 'build-store',
  assignedAgentIds: ['gemini', 'claude', 'codex'],
  startedAt: MOCK_ACTIVE_STARTED_AT,
  budget: '80k',
  policy: 'serial · retry 3',
  phases: mockActivePhases(),
  // Built from `phases` by the mock adapter, as Hermes detail is built by the HTTP adapter.
  executionGraph: [],
  changedFiles: MOCK_CHANGED_FILES,
  testSummary: {
    passed: 184,
    skipped: 2,
    failed: 0,
    duration: '18.4s',
    rawLog: `tests/state/test_redis_store.py ......... [ 62%]\ntests/state/test_migration.py ....s.... [ 91%]\ntests/state/test_ttl.py ....s [100%]\n186 collected · 184 passed · 2 skipped in 18.4s`
  },
  retryHistory: [
    { attempt: 1, phase: 'BUILD', status: 'failed', note: 'redis connection refused in sandbox; retried with local container' },
    { attempt: 2, phase: 'BUILD', status: 'passed', note: 'container connection successful' }
  ],
  retriesUsed: 1,
  maxRetries: 3,
  tokenBreakdown: [
    { agentId: 'gemini', agentName: 'Gemini', phase: 'BUILD', tokensFormatted: '30.4k', color: 'var(--lys-agent-gemini)', percentage: 38 },
    { agentId: 'claude', agentName: 'Claude', phase: 'HARDEN', tokensFormatted: '13.7k', color: 'var(--lys-agent-claude)', percentage: 17 },
    { agentId: 'codex', agentName: 'Codex', phase: 'VERIFY', tokensFormatted: '~19k', color: 'var(--lys-agent-codex)', percentage: 0 }
  ]
};
