import { AgentModelsMap } from '../types';

export const MOCK_AGENT_MODELS: AgentModelsMap = {
  gemini: {
    configured: { default: 'gemini-2.5-pro', effort: 'high' },
    allowed: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
    lastUsed: { model: 'gemini-2.5-pro', effort: 'high', source: 'phase' }
  },
  claude: {
    configured: { default: 'claude-3-7-sonnet', effort: null },
    allowed: ['claude-3-7-sonnet', 'claude-3-5-sonnet', 'claude-3-5-haiku'],
    lastUsed: { model: 'claude-3-7-sonnet', effort: null, source: 'config' }
  },
  codex: {
    configured: { default: 'gpt-6.1-sol', effort: 'low' },
    allowed: ['gpt-5-codex', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-6.1-sol'],
    lastUsed: { model: 'sonnet', effort: null, source: 'phase' }
  }
};
