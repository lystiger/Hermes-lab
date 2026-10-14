import { vi } from 'vitest';

/**
 * Responses shaped like the live Hermes API observed in docs/api-audit.md (GET only).
 * Used to prove that HTTP-mode screens render only what this data backs.
 */
export const LIVE_JOB_ID = 'run_20261014_140653_live-runner-e2e';

/** Old enough to fall outside the 24h window, so FAILED 24H is a real zero. */
const OLD_COMPLETED_AT = '2026-10-01T10:02:05Z';

export const LIVE_HEALTH = {
  status: 'ok',
  service: 'hermes',
  version: '0.1.0',
  uptimeSeconds: 1842,
  timestamp: '2026-10-14T07:36:00Z'
};

export const LIVE_AGENTS = [
  { id: 'gemini', displayName: 'Gemini', provider: 'Google AI Studio', model: 'gemini-2.5-pro', role: 'Implementation', capabilities: ['build'], status: 'IDLE', currentTask: null, activeTool: null, persona: null, presentation: null },
  { id: 'claude', displayName: 'Claude', provider: 'Anthropic', model: 'claude-opus', role: 'Architecture', capabilities: ['plan', 'review'], status: 'IDLE', currentTask: null, activeTool: null, persona: null, presentation: null },
  { id: 'codex', displayName: 'Codex', provider: 'OpenAI', model: 'codex', role: 'Verification', capabilities: ['test'], status: 'IDLE', currentTask: null, activeTool: null, persona: null, presentation: null }
];

/** The one historical FAILED job in the live sample: no active job exists. */
export const LIVE_JOB_SUMMARY = {
  id: LIVE_JOB_ID,
  sprintId: null,
  title: 'Live runner end-to-end',
  repository: 'lystiger/example',
  branch: 'feat/live-runner',
  priority: 'P1',
  status: 'FAILED',
  currentPhase: 'verify',
  assignedAgentIds: ['gemini', 'codex'],
  createdAt: '2026-10-01T09:00:00Z',
  startedAt: '2026-10-01T09:00:00Z',
  completedAt: OLD_COMPLETED_AT,
  progress: 0.5,
  blockedReason: null,
  repairCount: 0,
  replanCount: 0
};

export const LIVE_JOB_DETAIL = {
  ...LIVE_JOB_SUMMARY,
  phases: [
    { id: 'ph_build', name: 'build', order: 1, role: 'builder', agentId: 'gemini', status: 'SUCCEEDED', attempt: 1, durationMs: null, startedAt: null, completedAt: null, commitSha: null, changedFilesCount: null, detail: null },
    { id: 'ph_verify', name: 'verify', order: 2, role: 'verifier', agentId: 'codex', status: 'FAILED', attempt: 1, durationMs: null, startedAt: null, completedAt: null, commitSha: null, changedFilesCount: null, detail: null }
  ],
  tasks: [],
  observations: [],
  artifacts: [],
  errors: [{ type: 'FAILED_TESTS', message: '1 test failed' }],
  retryHistory: [],
  verification: null
};

export const LIVE_EXECUTION = {
  backends: [
    { name: 'subprocess', available: true, detail: 'local process runner' },
    { name: 'herdr', available: true, detail: 'herdr found on PATH' },
    { name: 'openrig', available: true, detail: 'daemon up' }
  ],
  resources: [],
  openrig: { daemon: 'up', ledger: { owners: 0, rigIds: [] } },
  takenAt: 1791961678984
};

export interface LiveOptions {
  /** Make GET /jobs fail with HTTP 500. */
  failJobs?: boolean;
  /** Replace the job list (e.g. to add an active job). */
  jobs?: unknown[];
}

export interface LiveResponse {
  status: number;
  body: unknown;
}

export function respond(pathname: string, options: LiveOptions): LiveResponse {
  if (pathname === '/health') return { status: 200, body: LIVE_HEALTH };
  if (pathname === '/agents') return { status: 200, body: LIVE_AGENTS };
  if (pathname === '/jobs') {
    if (options.failJobs) return { status: 500, body: { detail: 'jobs store unavailable' } };
    return { status: 200, body: options.jobs ?? [LIVE_JOB_SUMMARY] };
  }
  if (pathname === `/jobs/${LIVE_JOB_ID}`) return { status: 200, body: LIVE_JOB_DETAIL };
  if (pathname === '/threads') return { status: 200, body: [] };
  if (pathname === '/events') return { status: 200, body: [] };
  if (pathname === '/execution') return { status: 200, body: LIVE_EXECUTION };
  return { status: 404, body: { detail: `Not found: ${pathname}` } };
}

/** Installs a fetch stub that answers from the live sample. Call vi.unstubAllGlobals() afterwards. */
export function installLiveHermes(options: LiveOptions = {}) {
  const requests: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    requests.push(`${url.pathname}${url.search}`);
    const { status, body } = respond(url.pathname, options);
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 200 ? 'OK' : status === 404 ? 'Not Found' : 'Internal Server Error',
      json: async () => body
    } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, requests };
}
