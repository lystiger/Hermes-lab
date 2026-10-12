import { ActorRef, AgentSummary } from './types';

export const SYSTEM_ACTORS: Record<string, ActorRef> = {
  hermes: {
    id: 'hermes',
    kind: 'runtime',
    displayName: 'Hermes',
    accentColor: '#CBA35C'
  },
  hermes_runner: {
    id: 'hermes_runner',
    kind: 'runtime',
    displayName: 'Hermes Runner',
    accentColor: '#CBA35C'
  },
  herdr: {
    id: 'herdr',
    kind: 'runtime',
    displayName: 'Herdr',
    accentColor: '#8C949F'
  },
  // Legacy actor ID retained for events/messages created before the runtime was renamed.
  lysstack: {
    id: 'hermes',
    kind: 'runtime',
    displayName: 'Hermes',
    accentColor: '#CBA35C'
  },
  lyscontrol: {
    id: 'lyscontrol',
    kind: 'system',
    displayName: 'LysControl Console',
    accentColor: '#CBA35C'
  },
  operator: {
    id: 'operator',
    kind: 'operator',
    displayName: 'Operator',
    accentColor: '#E6E9ED',
    subtitle: 'Human Operator'
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
      const avatarUrl =
        foundAgent.presentation?.avatarUrl ||
        foundAgent.persona?.visual?.avatar;
      const subtitle =
        foundAgent.presentation?.subtitle ||
        foundAgent.persona?.visual?.subtitle ||
        foundAgent.persona?.summary ||
        foundAgent.role;

      return {
        id: foundAgent.id,
        kind: 'agent',
        displayName: foundAgent.displayName,
        accentColor: foundAgent.presentation?.accentColor || '#8C949F',
        avatarUrl,
        subtitle
      };
    }
  }

  // 2. Look up in known system actors
  if (SYSTEM_ACTORS[normalized]) {
    return SYSTEM_ACTORS[normalized];
  }

  // Runtime event sources include component suffixes such as hermes.scheduler.
  // Historical LysStack-prefixed runtime events use the same presentation.
  const runtimePrefix = normalized.split('.', 1)[0];
  if (runtimePrefix === 'hermes' || runtimePrefix === 'lysstack') {
    return { ...SYSTEM_ACTORS.hermes, id: normalized };
  }

  // 3. Generic unknown actor fallback (support any open string ID)
  return {
    id: normalized,
    kind: 'agent',
    displayName: rawIdentifier.charAt(0).toUpperCase() + rawIdentifier.slice(1),
    accentColor: '#8C949F'
  };
}
