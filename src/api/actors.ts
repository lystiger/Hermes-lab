import { ActorRef, AgentSummary } from './types';
import { actorAccent, agentAccent, NEUTRAL_ACCENT } from '../theme/agents';

export const SYSTEM_ACTORS: Record<string, ActorRef> = {
  hermes: {
    id: 'hermes',
    kind: 'runtime',
    displayName: 'Hermes',
    accentColor: agentAccent('hermes'),
    avatarUrl: '/agents/hermes.webp',
    subtitle: 'Orchestrator'
  },
  hermes_runner: {
    id: 'hermes_runner',
    kind: 'runtime',
    displayName: 'Hermes Runner',
    accentColor: agentAccent('hermes')
  },
  herdr: {
    id: 'herdr',
    kind: 'runtime',
    displayName: 'Herdr',
    accentColor: NEUTRAL_ACCENT
  },
  // D-009 execution backends (source_kind="runtime", source_id=<backend>)
  openrig: {
    id: 'openrig',
    kind: 'runtime',
    displayName: 'OpenRig',
    accentColor: 'var(--lys-accent-sky)'
  },
  subprocess: {
    id: 'subprocess',
    kind: 'runtime',
    displayName: 'Subprocess',
    accentColor: NEUTRAL_ACCENT
  },
  // Legacy actor ID retained for events/messages created before the runtime was renamed.
  lysstack: {
    id: 'hermes',
    kind: 'runtime',
    displayName: 'Hermes',
    accentColor: agentAccent('hermes'),
    avatarUrl: '/agents/hermes.webp',
    subtitle: 'Orchestrator'
  },
  lyscontrol: {
    id: 'lyscontrol',
    kind: 'system',
    displayName: 'LysControl Console',
    accentColor: agentAccent('hermes')
  },
  operator: {
    id: 'operator',
    kind: 'operator',
    displayName: 'Operator',
    accentColor: 'var(--lys-text-primary)',
    subtitle: 'Human Operator'
  },
  pytest: {
    id: 'pytest',
    kind: 'tool',
    displayName: 'pytest-runner',
    accentColor: 'var(--lys-status-success)'
  }
};

/**
 * Name shown for an event's source: the registered name for a known actor (for example "OpenRig" rather than the
 * raw id "openrig"), otherwise the name the event itself carries.
 */
export function traceSourceName(source: { id: string; displayName: string }): string {
  return SYSTEM_ACTORS[source.id.toLowerCase()]?.displayName ?? source.displayName;
}

/**
 * Resolves an actor presentation reference from dynamic agent registry, known system actors, or generic fallback.
 */
export function resolveActorPresentation(
  rawIdentifier?: string,
  agentRegistry?: Record<string, AgentSummary> | AgentSummary[]
): ActorRef {
  if (!rawIdentifier) {
    return { id: 'unknown', kind: 'system', displayName: '—', accentColor: NEUTRAL_ACCENT };
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
        accentColor: actorAccent(foundAgent.id, foundAgent.presentation?.accentColor),
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
    accentColor: agentAccent(normalized) || NEUTRAL_ACCENT
  };
}
