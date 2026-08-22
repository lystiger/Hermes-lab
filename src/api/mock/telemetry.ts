import { ProviderQuota, ProjectionItem, SettingItem, OverviewTelemetry } from '../types';

export const MOCK_TELEMETRY: OverviewTelemetry = {
  runningJobsCount: 2,
  queuedJobsCount: 4,
  blockedJobsCount: 1,
  failed24hCount: 0,
  tokensToday: '284K',
  estSpendToday: '$4.12',
  sprintBudgetUsedPct: 58
};

export const MOCK_PROVIDER_QUOTAS: ProviderQuota[] = [
  {
    id: 'claude',
    name: 'CLAUDE',
    color: '#D9A05B',
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
    id: 'codex',
    name: 'CODEX',
    color: '#4EC9A0',
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
    id: 'gemini',
    name: 'ANTIGRAVITY / GEMINI',
    color: '#5B8CFF',
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
    id: 'herdr',
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

export const MOCK_PROJECTIONS: ProjectionItem[] = [
  { id: '#145', task: 'Queue scheduler regression tests', est: '~22k', w: '24%', wLow: '18%', color: '#4EC9A0', conf: 'medium' },
  { id: '#146', task: 'Frontend accessibility audit', est: '~14k', w: '15%', wLow: '12%', color: '#5B8CFF', conf: 'high' },
  { id: '#147', task: 'Memory compaction policy', est: '~27k', w: '30%', wLow: '21%', color: '#D9A05B', conf: 'medium' },
  { id: '#148', task: 'Redis client compat matrix', est: '~16–34k', w: '37%', wLow: '18%', color: '#E3A008', conf: 'low' }
];

export const MOCK_RUNTIME_SETTINGS: SettingItem[] = [
  { label: 'hermes orchestrator', value: 'running · pid 4188', color: '#3FB950' },
  { label: 'herdr sandbox', value: 'local container', color: '#E6E9ED' },
  { label: 'state store', value: 'redis://localhost:6379', color: '#E6E9ED' },
  { label: 'trace retention', value: '14 days', color: '#E6E9ED' },
  { label: 'reduced motion', value: 'follow system', color: '#8C949F' }
];

export const MOCK_POLICY_SETTINGS: SettingItem[] = [
  { label: 'sprint budget', value: '300k tokens', color: '#E6E9ED' },
  { label: 'per-job cap', value: '80k tokens', color: '#E6E9ED' },
  { label: 'hard stop', value: 'pause at 246k', color: '#F2555A' },
  { label: 'retries per phase', value: '3', color: '#E6E9ED' },
  { label: 'concurrency policy', value: 'serial per repository', color: '#E6E9ED' }
];
