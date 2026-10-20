import React from 'react';
import { AgentWorkspace } from '../../features/agents/AgentWorkspace';

/** /agents: roster and the first agent's dossier. Selecting another agent opens its URL. */
export const AgentsListRoute: React.FC = () => <AgentWorkspace />;

export default AgentsListRoute;
