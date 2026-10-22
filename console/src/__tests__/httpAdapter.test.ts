import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HttpHermesApi } from '../api/adapters/httpAdapter';

/** Every request carries a timeout signal (see REQUEST_TIMEOUT_MS in httpAdapter). */
const TIMED = expect.objectContaining({ signal: expect.anything() });

describe('HttpHermesApi Contract Implementation', () => {
  const baseUrl = 'http://localhost:8000';
  let api: HttpHermesApi;

  beforeEach(() => {
    api = new HttpHermesApi(baseUrl);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches and maps /health status successfully', async () => {
    const mockHealth = {
      status: 'ok',
      service: 'hermes',
      version: '0.1.0',
      uptimeSeconds: 1842,
      timestamp: '2026-08-22T08:00:00Z'
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth
    } as any);

    const health = await api.getHealth();
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/health', TIMED);
    expect(health.status).toBe('ok');
    expect(health.service).toBe('hermes');
    expect(health.uptimeSeconds).toBe(1842);
  });

  it('throws an informative error if /health returns non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable'
    } as any);

    await expect(api.getHealth()).rejects.toThrow('HTTP 503: Service Unavailable');
  });

  it('fetches dynamic agent list and enhances presentation cleanly', async () => {
    const mockBackendAgents = [
      {
        id: 'gemini',
        displayName: 'Gemini',
        provider: 'Google AI Studio',
        model: 'antigravity-2.5-pro',
        role: 'Implementation',
        capabilities: ['build', 'refactoring'],
        status: 'RUNNING'
      },
      {
        id: 'custom-subagent',
        displayName: 'Custom Subagent',
        provider: 'Local',
        model: 'local-v1',
        role: 'Arbitrary Task Execution',
        capabilities: ['testing'],
        status: 'IDLE'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBackendAgents
    } as any);

    const agents = await api.getAgents();
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/agents', TIMED);
    expect(agents.length).toBe(2);

    const gemini = agents.find((a) => a.id === 'gemini');
    expect(gemini?.displayName).toBe('Gemini');
    expect(gemini?.status).toBe('RUNNING');
    expect(gemini?.presentation?.avatarUrl).toBeUndefined();
    expect(gemini?.presentation?.characterCardUrl).toBeUndefined();

    const custom = agents.find((a) => a.id === 'custom-subagent');
    expect(custom?.displayName).toBe('Custom Subagent');
    expect(custom?.status).toBe('IDLE');
    expect(custom?.presentation?.accentColor).toBeDefined();
  });

  it('returns truthful unobserved telemetry for getAgent in real mode (no fabricated stats)', async () => {
    const mockBackendAgents = [
      {
        id: 'claude',
        displayName: 'Claude',
        provider: 'Anthropic API',
        model: 'claude-sonnet-4-5',
        role: 'Architecture',
        capabilities: ['security-review'],
        status: 'IDLE'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBackendAgents
    } as any);

    const detail = await api.getAgent('claude');
    expect(detail).not.toBeNull();
    expect(detail?.id).toBe('claude');
    expect(detail?.input).toBe('—');
    expect(detail?.output).toBe('—');
    expect(detail?.activity).toEqual([]);
    expect(detail?.runs).toEqual([]);
  });

  it('fetches real jobs from GET /jobs (Phase 4)', async () => {
    const mockJobs = [
      {
        id: 'run_20260822_unigreen_01',
        sprintId: 'unigreen-inquiry-v1',
        title: 'Unigreen Inquiry Delivery',
        repository: 'Unigreen',
        branch: 'hermes/unigreen-inquiry-v1/integration',
        priority: 'P1',
        status: 'RUNNING',
        assignedAgentIds: ['gemini', 'claude', 'codex'],
        createdAt: '2026-08-22T08:00:00Z',
        startedAt: '2026-08-22T08:01:00Z'
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockJobs
    } as any);

    const jobs = await api.getJobs();
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/jobs?', TIMED);
    expect(jobs.length).toBe(1);
    expect(jobs[0].id).toBe('run_20260822_unigreen_01');
    expect(jobs[0].status).toBe('RUNNING');
    expect(jobs[0].assignedAgentIds).toEqual(['gemini', 'claude', 'codex']);
  });

  it('fetches real job detail and maps generic phases to execution graph (Phase 4)', async () => {
    const mockJobDetail = {
      id: 'run_20260822_unigreen_01',
      sprintId: 'unigreen-inquiry-v1',
      title: 'Unigreen Inquiry Delivery',
      repository: 'Unigreen',
      branch: 'hermes/unigreen-inquiry-v1/integration',
      priority: 'P1',
      status: 'RUNNING',
      assignedAgentIds: ['gemini', 'claude', 'codex'],
      phases: [
        { id: 'p1', name: 'BUILD', order: 1, role: 'builder', agentId: 'gemini', status: 'SUCCEEDED', commitSha: 'sha123' },
        { id: 'p2', name: 'HARDEN', order: 2, role: 'hardener', agentId: 'claude', status: 'RUNNING' },
        { id: 'p3', name: 'VERIFY', order: 3, role: 'verifier', agentId: 'codex', status: 'PENDING' }
      ],
      artifacts: [
        { id: 'art1', type: 'git_commit', label: 'Commit', ref: 'sha123' }
      ]
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockJobDetail
    } as any);

    const detail = await api.getJob('run_20260822_unigreen_01');
    expect(detail).not.toBeNull();
    expect(detail?.phases?.length).toBe(3);
    expect(detail?.executionGraph.length).toBe(3);
    expect(detail?.executionGraph[0].state).toBe('COMPLETED');
    expect(detail?.executionGraph[1].state).toBe('RUNNING');
    expect(detail?.executionGraph[2].state).toBe('QUEUED');
  });

  it('handles job cancellation through POST /jobs/:id/cancel (Phase 4)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cancelled: true })
    } as any);

    const success = await api.triggerJobAction('run_test_01', 'cancel');
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/jobs/run_test_01/cancel', expect.objectContaining({
      method: 'POST'
    }));
    expect(success).toBe(true);
  });

  it('handles SSE streaming subscription with cursor and clean unsubscription', () => {
    let messageListener: any = null;
    let closed = false;
    let openedUrl = '';

    class MockEventSource {
      constructor(public url: string) {
        openedUrl = url;
      }
      addEventListener(type: string, listener: any) {
        if (type === 'trace') {
          messageListener = listener;
        }
      }
      removeEventListener() {}
      close() {
        closed = true;
      }
    }

    (global as any).EventSource = MockEventSource;

    const handler = vi.fn();
    const sub = api.subscribeEvents(handler, undefined, 'evt_050');

    expect(openedUrl).toBe('http://localhost:8000/events/stream?after=evt_050');
    expect(messageListener).toBeDefined();

    const sampleEventDTO = {
      id: 'evt_200',
      ts: '10:45:00.000',
      rawTs: 1771663500,
      source: {
        id: 'gemini',
        kind: 'agent',
        displayName: 'Gemini'
      },
      kind: 'phase.started',
      detail: 'Starting sprint build phase'
    };

    messageListener({ data: JSON.stringify(sampleEventDTO) });

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'evt_200',
        kind: 'phase.started',
        detail: 'Starting sprint build phase'
      })
    );

    sub.unsubscribe();
    expect(closed).toBe(true);
  });

  it("fetches operational threads and maps participants", async () => {
    const mockThreads = [
      {
        id: "thread_job_run_1",
        jobId: "run_1",
        title: "Sprint 1",
        participants: [{ id: "gemini", kind: "agent", displayName: "Gemini" }],
        createdAt: "2026-08-22T10:00:00Z",
        updatedAt: "2026-08-22T10:05:00Z"
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockThreads
    } as any);

    const threads = await api.getThreads("run_1");
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/threads?jobId=run_1", TIMED);
    expect(threads.length).toBe(1);
    expect(threads[0].id).toBe("thread_job_run_1");
    expect(threads[0].participants[0].displayName).toBe("Gemini");
  });

  it("fetches operational messages for a thread", async () => {
    const mockMessages = [
      {
        id: "msg_1",
        threadId: "thread_job_run_1",
        from: { id: "gemini", kind: "agent", displayName: "Gemini" },
        to: [{ id: "claude", kind: "agent", displayName: "Claude" }],
        kind: "handoff",
        intent: "review_request",
        text: "BUILD completed.",
        artifactRefs: [{ id: "art_1", type: "git_commit", label: "commit 1", ref: "8a21fc9" }],
        createdAt: "2026-08-22T10:01:00Z"
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockMessages
    } as any);

    const messages = await api.getMessages("thread_job_run_1");
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/threads/thread_job_run_1/messages?", TIMED);
    expect(messages.length).toBe(1);
    expect(messages[0].text).toBe("BUILD completed.");
    expect(messages[0].intent).toBe("review_request");
    expect(messages[0].artifactRefs?.[0].ref).toBe("8a21fc9");
  });

  it("sends operator message to control plane", async () => {
    const mockCreated = {
      id: "msg_op_1",
      threadId: "thread_job_run_1",
      from: { id: "operator", kind: "operator", displayName: "Operator" },
      to: [{ id: "claude", kind: "agent", displayName: "Claude" }],
      kind: "operator",
      text: "Focus on cleanup.",
      createdAt: "2026-08-22T10:02:00Z"
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockCreated
    } as any);

    const res = await api.sendMessage("thread_job_run_1", "Focus on cleanup.", ["claude"], "operator");
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/messages",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          threadId: "thread_job_run_1",
          text: "Focus on cleanup.",
          to: ["claude"],
          kind: "operator",
          intent: undefined
        })
      })
    );
    expect(res.id).toBe("msg_op_1");
    expect(res.from.displayName).toBe("Operator");
  });

  it("fetches agent inbox mailbox entries", async () => {
    const mockInbox = [
      {
        messageId: "msg_1",
        recipientId: "claude",
        state: "DELIVERED",
        receivedAt: "2026-08-22T10:01:00Z"
      }
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockInbox
    } as any);

    const inbox = await api.getAgentInbox("claude");
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:8000/agents/claude/inbox?", TIMED);
    expect(inbox.length).toBe(1);
    expect(inbox[0].recipientId).toBe("claude");
  });

  it('keeps the execution snapshot takenAt cutoff from the real API', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ backends: [], resources: [], openrig: null, takenAt: 1760420000.5 })
    });

    const snapshot = await api.getExecutionSnapshot();

    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/execution', TIMED);
    expect(snapshot.takenAt).toBe(1760420000.5);
  });

  it('omits takenAt when the API does not send one', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ backends: [], resources: [], openrig: null })
    });

    expect((await api.getExecutionSnapshot()).takenAt).toBeUndefined();
  });
});
