import { AgentData, JobItem, PipelineStep, ProviderQuota, TraceEvent } from './types';
import { AGENTS_MAP, INITIAL_QUEUE, INITIAL_PIPELINE, PROVIDER_QUOTAS } from './mockData';

export class LysControlApi {
  static async getAgents(): Promise<AgentData[]> {
    return Object.values(AGENTS_MAP);
  }

  static async getAgentById(id: string): Promise<AgentData | undefined> {
    const key = Object.keys(AGENTS_MAP).find(k => k.toLowerCase() === id.toLowerCase());
    return key ? AGENTS_MAP[key] : undefined;
  }

  static async getQueue(): Promise<JobItem[]> {
    return [...INITIAL_QUEUE];
  }

  static async getPipeline(): Promise<PipelineStep[]> {
    return [...INITIAL_PIPELINE];
  }

  static async getProviderQuotas(): Promise<ProviderQuota[]> {
    return [...PROVIDER_QUOTAS];
  }

  static async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    console.log(`[LysControl API] Triggered ${action} on job ${jobId}`);
    return true;
  }

  static async dispatchAgentMessage(agentId: string, message: string): Promise<{ success: boolean; response: string }> {
    console.log(`[LysControl API] Message dispatched to ${agentId}: ${message}`);
    return {
      success: true,
      response: `[${agentId}] Received command: "${message}". Processed in local execution context.`
    };
  }
}
