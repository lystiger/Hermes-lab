import { ActorRef } from '../types';

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

export function resolveActorRef(rawIdentifier: string, defaultKind: 'agent' | 'system' | 'runtime' | 'tool' = 'agent', defaultColor: string = '#8C949F'): ActorRef {
  const normalized = rawIdentifier.toLowerCase();
  if (SYSTEM_ACTORS[normalized]) {
    return SYSTEM_ACTORS[normalized];
  }
  return {
    id: normalized,
    kind: defaultKind,
    displayName: rawIdentifier,
    accentColor: defaultColor
  };
}
