import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import OverviewRoute from './routes/index';
import QueueRoute from './routes/queue';
import AgentsListRoute from './routes/agents/index';
import AgentDetailRoute from './routes/agents/$agentId';
import UsageRoute from './routes/usage';
import EventsRoute from './routes/events';
import ExecutionRoute from './routes/execution';
import SettingsRoute from './routes/settings';

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<OverviewRoute />} />
        <Route path="queue" element={<QueueRoute />} />
        <Route path="agents" element={<AgentsListRoute />} />
        <Route path="agents/:agentId" element={<AgentDetailRoute />} />
        <Route path="usage" element={<UsageRoute />} />
        <Route path="events" element={<EventsRoute />} />
        <Route path="execution" element={<ExecutionRoute />} />
        <Route path="settings" element={<SettingsRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
};

export default App;
