import React from 'react';
import { useParams } from 'react-router-dom';
import { AgentWorkspace } from '../../features/agents/AgentWorkspace';

/** /agents/:agentId: roster with this agent's dossier open. */
export const AgentDetailRoute: React.FC = () => {
  const { agentId } = useParams<{ agentId: string }>();
  return <AgentWorkspace selectedId={agentId} />;
};

export default AgentDetailRoute;
