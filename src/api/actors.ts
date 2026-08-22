import { ActorRef, AgentSummary } from './types';

export const SYSTEM_ACTORS: Record<string, ActorRef> = {
  hermes: {
    id: 'hermes',
    kind: 'runtime',
    displayName: 'Hermes',
    accentColor: '#CBA35C'
  },
  herdr: {
    id: 'herdr',
    kind: 'runtime',
    displayName: 'Herdr',
    accentColor: '#8C949F'
  },
  lysstack: {
    id: 'lysstack',
    kind: 'system',
    displayName: 'LysStack Control Plane',
    accentColor: '#CBA35C'
  },
  lyscontrol: {
    id: 'lyscontrol',
    kind: 'system',
    displayName: 'LysControl Console',
    accentColor: '#CBA35C'
  },
  pytest: {
    id: 'pytest',
    kind: 'tool',
    displayName: 'pytest-runner',
    accentColor: '#3FB950'
  }
};

/**
 * Resolves an actor presentation reference from dynamic agent registry, known system actors, or generic fallback.
 */
export function resolveActorPresentation(
  rawIdentifier?: string,
  agentRegistry?: Record<string, AgentSummary> | AgentSummary[]
): ActorRef {
  if (!rawIdentifier) {
    return { id: 'unknown', kind: 'system', displayName: '—', accentColor: '#8C949F' };
  }

  const normalized = rawIdentifier.toLowerCase();

  // 1. Look up in dynamic agent registry
  if (agentRegistry) {
    const foundAgent = Array.isArray(agentRegistry)
      ? agentRegistry.find((a) => a.id.toLowerCase() === normalized)
      : agentRegistry[normalized];

    if (foundAgent) {
      return {
        id: foundAgent.id,
        kind: 'agent',
        displayName: foundAgent.displayName,
        accentColor: foundAgent.presentation?.accentColor || '#8C949F'
      };
    }
  }

  // 2. Look up in known system actors
  if (SYSTEM_ACTORS[normalized]) {
    return SYSTEM_ACTORS[normalized];
  }

  // 3. Generic unknown actor fallback
  return {
    id: normalized,
    kind: 'agent',
    displayName: rawIdentifier.charAt(0).toUpperCase() + rawIdentifier.slice(1),
    accentColor: '#8C949F'
  };
}
