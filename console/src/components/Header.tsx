import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAgent } from '../api/hooks';

export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId?: string }>();
  const { agent } = useAgent(agentId);

  const pathname = location.pathname;

  let title = '';
  let crumb = '';
  let backPath = '';

  if (pathname.startsWith('/agents/')) {
    title = agent?.displayName || agentId || 'Agent';
    crumb = 'Agents';
    backPath = '/agents';
  }

  // The bar only exists to link back from an agent's page; other pages get the space back.
  if (!crumb) return null;

  return (
    <header className="h-[44px] flex-shrink-0 flex items-center justify-between px-5 border-b border-lys-subtle bg-lys-base select-none">
      <div className="flex items-center gap-3 min-w-0">
        {crumb ? (
          <>
            <button onClick={() => navigate(backPath)} className="text-[12px] text-lys-faint hover:text-lys-primary cursor-pointer transition-colors">
              ← {crumb}
            </button>
            <span className="text-[12px] text-lys-muted break-words" title={title}>{title}</span>
          </>
        ) : null}
      </div>

    </header>
  );
};

export default Header;
