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

export const LIVE_AGENT_MODELS = {
  gemini: {
    configured: { default: 'gemini-2.5-pro', effort: 'high' },
    allowed: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
    lastUsed: { model: 'gemini-2.5-pro', effort: 'high', source: 'phase' }
  },
  claude: {
    configured: null,
    allowed: ['claude-3-7-sonnet', 'claude-3-5-sonnet', 'claude-3-5-haiku'],
    lastUsed: null
  },
  codex: {
    configured: { default: 'gpt-6.1-sol', effort: 'low' },
    allowed: ['gpt-5-codex', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-6.1-sol'],
    lastUsed: { model: 'sonnet', effort: null, source: 'phase' }
  }
};

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

/** GET /capacity/telemetry as observed on the live service (no providers recorded yet). */
export const LIVE_CAPACITY = {
  timestamp: '2026-10-14T07:57:35.236695+00:00',
  summary: {
    total_providers: 0,
    total_requests: 0,
    total_failures: 0,
    total_throttling_events: 0,
    total_tokens: 0,
    input_tokens: 0,
    output_tokens: 0,
    cached_tokens: 0
  },
  providers: {},
  jobs_tracked: 0
};

/** GET /jobs/{id}/telemetry as observed for the sample job. */
export const LIVE_JOB_TELEMETRY = {
  job_id: LIVE_JOB_ID,
  tokens: { input_tokens: 0, output_tokens: 0, cached_tokens: 0, total_tokens: 0 }
};

export interface LiveOptions {
  /** Make GET /jobs fail with HTTP 500. */
  failJobs?: boolean;
  /** Replace the job list (e.g. to add an active job). */
  jobs?: unknown[];
  /** Per-collection overrides for the sample job. Unset means the observed empty collection. */
  tasks?: unknown[];
  runs?: unknown[];
  observations?: unknown[];
  events?: unknown[];
  /** Make a sub-resource fail with HTTP 500, e.g. 'tasks' or 'events'. */
  failSub?: string;
  /** Make the sample job's telemetry return the given token totals. */
  jobTokens?: { input_tokens: number; output_tokens: number; cached_tokens: number; total_tokens: number };
  /** GET /capacity/limits override. */
  limits?: unknown;
  /** Capacity report override (e.g. providers recorded). */
  capacity?: unknown;
  /** Recoverable job list. */
  recoverable?: unknown[];
  /** Make /threads/{id}/messages return 404 (thread does not exist). */
  threadMissing?: boolean;
  /** Simulate Hermes being down: every request fails at the network level. */
  unreachable?: boolean;
  /** Make GET /agents/models fail with HTTP 500 */
  failModels?: boolean;
  /** Override models response */
  models?: unknown;
  /** Make PUT /agents/:id/model fail */
  failModelPut?: boolean;
  failModelPutDetail?: string;
  modelPutResponse?: unknown;
}

export interface LiveResponse {
  status: number;
  body: unknown;
}

export function respond(pathname: string, options: LiveOptions): LiveResponse {
  if (pathname === '/health') return { status: 200, body: LIVE_HEALTH };
  if (pathname === '/agents') return { status: 200, body: LIVE_AGENTS };
  if (pathname === '/agents/models') {
    if (options.failModels) return { status: 500, body: { detail: 'models store unavailable' } };
    return { status: 200, body: options.models ?? LIVE_AGENT_MODELS };
  }
  const modelPutMatch = pathname.match(/^\/agents\/([^/]+)\/model$/);
  if (modelPutMatch) {
    if (options.failModelPut) {
      return { status: 400, body: { detail: options.failModelPutDetail || 'model not allowed' } };
    }
    return { status: 200, body: options.modelPutResponse ?? { default: 'gpt-6.1-sol', effort: 'low' } };
  }
  if (pathname === '/jobs') {
    if (options.failJobs) return { status: 500, body: { detail: 'jobs store unavailable' } };
    return { status: 200, body: options.jobs ?? [LIVE_JOB_SUMMARY] };
  }
  if (pathname === `/jobs/${LIVE_JOB_ID}`) return { status: 200, body: LIVE_JOB_DETAIL };
  if (pathname === '/threads') return { status: 200, body: [] };
  if (pathname === '/events') return { status: 200, body: [] };
  if (pathname === '/execution') return { status: 200, body: LIVE_EXECUTION };
  if (pathname === '/capacity/telemetry') return { status: 200, body: options.capacity ?? LIVE_CAPACITY };
  if (pathname === '/capacity/limits') return { status: 200, body: options.limits ?? { timestamp: '2026-10-14T07:36:00Z', agents: [] } };
  if (pathname === '/jobs/recoverable') return { status: 200, body: options.recoverable ?? [] };
  if (pathname === `/jobs/${LIVE_JOB_ID}/telemetry`) {
    return {
      status: 200,
      body: options.jobTokens ? { job_id: LIVE_JOB_ID, tokens: options.jobTokens } : LIVE_JOB_TELEMETRY
    };
  }
  const sub = pathname.match(/^\/jobs\/[^/]+\/(tasks|runs|observations|events)$/);
  if (sub) {
    const name = sub[1];
    if (options.failSub === name) return { status: 500, body: { detail: `${name} store unavailable` } };
    const bodies: Record<string, unknown[] | undefined> = {
      tasks: options.tasks,
      runs: options.runs,
      observations: options.observations,
      events: options.events
    };
    return { status: 200, body: bodies[name] ?? [] };
  }
  if (/^\/threads\/[^/]+\/messages$/.test(pathname)) {
    return options.threadMissing
      ? { status: 404, body: { detail: 'Thread not found' } }
      : { status: 200, body: [] };
  }
  return { status: 404, body: { detail: `Not found: ${pathname}` } };
}

/** Installs a fetch stub that answers from the live sample. Call vi.unstubAllGlobals() afterwards. */
export function installLiveHermes(options: LiveOptions = {}) {
  const requests: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    requests.push(`${url.pathname}${url.search}`);
    if (options.unreachable) throw new TypeError('Failed to fetch');
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
