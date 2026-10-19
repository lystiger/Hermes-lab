import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.hoisted(() => {
  delete process.env.VITE_LYSCONTROL_MOCK;
});

import { HttpHermesApi } from '../api/adapters/httpAdapter';
import { MockHermesApi } from '../api/adapters/mockAdapter';
import { HermesUnreachableError } from '../api/connection';

describe('M8 Models Adapter Contract Tests', () => {
  let api: HttpHermesApi;
  const baseUrl = 'http://localhost:8000';

  beforeEach(() => {
    api = new HttpHermesApi(baseUrl);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('GET /agents/models', () => {
    it('parses observed shape with configured, allowed, and lastUsed models', async () => {
      const mockResponse = {
        gemini: {
          configured: { default: 'gemini-2.5-pro', effort: 'high' },
          allowed: ['gemini-2.5-pro', 'gemini-2.5-flash'],
          lastUsed: { model: 'gemini-2.5-pro', effort: 'high', source: 'phase' }
        },
        codex: {
          configured: { default: 'gpt-6.1-sol', effort: 'low' },
          allowed: ['gpt-5-codex', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-6.1-sol'],
          lastUsed: { model: 'sonnet', effort: null, source: 'phase' }
        }
      };

      vi.stubGlobal('fetch', vi.fn(async (url: string | URL) => {
        expect(String(url)).toBe(`${baseUrl}/agents/models`);
        return {
          ok: true,
          status: 200,
          json: async () => mockResponse
        } as Response;
      }));

      const res = await api.getAgentModels();
      expect(res.codex.configured?.default).toBe('gpt-6.1-sol');
      expect(res.codex.configured?.effort).toBe('low');
      expect(res.codex.allowed).toEqual(['gpt-5-codex', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-6.1-sol']);
      expect(res.codex.lastUsed?.model).toBe('sonnet');
      expect(res.codex.lastUsed?.effort).toBeNull();
      expect(res.codex.lastUsed?.source).toBe('phase');
    });

    it('correctly handles null configured, null default, null lastUsed and various sources', async () => {
      const mockResponse = {
        claude: {
          configured: null,
          allowed: ['claude-3-7-sonnet', 'claude-3-5-sonnet'],
          lastUsed: null
        },
        gemini: {
          configured: { default: null, effort: null },
          allowed: ['gemini-2.5-pro'],
          lastUsed: { model: 'gemini-2.5-pro', effort: null, source: 'cli-default' }
        },
        codex: {
          configured: { default: 'gpt-5-codex', effort: 'xhigh' },
          allowed: ['gpt-5-codex'],
          lastUsed: { model: 'gpt-5-codex', effort: 'minimal', source: 'config' }
        }
      };

      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => mockResponse
      }) as Response));

      const res = await api.getAgentModels();
      expect(res.claude.configured).toBeNull();
      expect(res.claude.lastUsed).toBeNull();
      expect(res.gemini.configured?.default).toBeNull();
      expect(res.gemini.lastUsed?.source).toBe('cli-default');
      expect(res.codex.lastUsed?.source).toBe('config');
    });

    it('throws HermesUnreachableError on network failure', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }));

      await expect(api.getAgentModels()).rejects.toThrow(HermesUnreachableError);
    });

    it('throws on HTTP 500 error from /agents/models', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'server failure' })
      }) as Response));

      await expect(api.getAgentModels()).rejects.toThrow('HTTP 500');
    });
  });

  describe('PUT /agents/{id}/model', () => {
    it('sends model and effort payload and returns 200 response', async () => {
      let capturedBody: any;
      let capturedMethod: string | undefined;

      vi.stubGlobal('fetch', vi.fn(async (url: string | URL, init?: RequestInit) => {
        expect(String(url)).toBe(`${baseUrl}/agents/codex/model`);
        capturedMethod = init?.method;
        capturedBody = JSON.parse(init?.body as string);
        return {
          ok: true,
          status: 200,
          json: async () => ({ default: 'gpt-5-codex', effort: 'low' })
        } as Response;
      }));

      const res = await api.setAgentModel('codex', 'gpt-5-codex', 'low');
      expect(capturedMethod).toBe('PUT');
      expect(capturedBody).toEqual({ model: 'gpt-5-codex', effort: 'low' });
      expect(res).toEqual({ default: 'gpt-5-codex', effort: 'low' });
    });

    it('sends effort as null when effort is omitted or null', async () => {
      let capturedBody: any;

      vi.stubGlobal('fetch', vi.fn(async (_url: string | URL, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return {
          ok: true,
          status: 200,
          json: async () => ({ default: 'claude-3-7-sonnet', effort: null })
        } as Response;
      }));

      const res = await api.setAgentModel('claude', 'claude-3-7-sonnet');
      expect(capturedBody).toEqual({ model: 'claude-3-7-sonnet', effort: null });
      expect(res.effort).toBeNull();
    });

    it('surfaces 400 error body detail when model or effort is not allowed', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: "Model 'gpt-invalid' is not in allowed list" })
      }) as Response));

      await expect(api.setAgentModel('codex', 'gpt-invalid', 'low')).rejects.toThrow(
        "Model 'gpt-invalid' is not in allowed list"
      );
    });

    it('surfaces 404 error detail when agent is unknown', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: "Agent 'unknown-agent' not found" })
      }) as Response));

      await expect(api.setAgentModel('unknown-agent', 'gpt-5-codex')).rejects.toThrow(
        "Agent 'unknown-agent' not found"
      );
    });
  });

  describe('MockHermesApi implementation', () => {
    it('returns mock models and allows updating model configuration', async () => {
      const mockApi = new MockHermesApi();
      const models = await mockApi.getAgentModels();
      expect(models.codex.allowed).toContain('gpt-6.1-sol');
      expect(models.gemini.allowed).toContain('gemini-2.5-pro');

      const updated = await mockApi.setAgentModel('codex', 'gpt-5-codex', 'medium');
      expect(updated).toEqual({ default: 'gpt-5-codex', effort: 'medium' });

      const reloaded = await mockApi.getAgentModels();
      expect(reloaded.codex.configured?.default).toBe('gpt-5-codex');
      expect(reloaded.codex.configured?.effort).toBe('medium');
    });

    it('rejects with error when model is not in allowed list in mock mode', async () => {
      const mockApi = new MockHermesApi();
      await expect(mockApi.setAgentModel('codex', 'forbidden-model')).rejects.toThrow(
        "Model 'forbidden-model' is not allowed for codex"
      );
    });
  });
});
