import React from 'react';
import { NavLink } from 'react-router-dom';
import { AnimatedCube } from './AnimatedCube';
import { useConsoleStore } from '../stores/useConsoleStore';

interface NavItem {
  to: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview' },
  { to: '/queue', label: 'Queue', badge: '4' },
  { to: '/agents', label: 'Agents', badge: '3' },
  { to: '/usage', label: 'Usage' },
  { to: '/events', label: 'Events', badge: 'live', badgeColor: '#3FB950' },
  { to: '/settings', label: 'Settings' }
];

export const Sidebar: React.FC = () => {
  const { clock } = useConsoleStore();

  return (
    <aside className="w-52 flex-shrink-0 bg-[#0C0E11] border-r border-[#1F242B] flex flex-col py-4 select-none">
      {/* Brand Header */}
      <div className="flex items-center gap-2.5 px-4 pb-4.5">
        <AnimatedCube size={26} />
        <div className="text-[12px] font-bold tracking-[0.16em] text-[#E6E9ED]">
          LYSCONTROL
        </div>
      </div>

      {/* Nav List */}
      <nav className="flex flex-col gap-0.5 mt-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `
              flex items-center justify-between px-4 py-2 text-[13px] transition-colors border-l-2
              ${isActive 
                ? 'border-[#CBA35C] bg-[#14171C] text-[#E6E9ED]' 
                : 'border-transparent text-[#8C949F] hover:bg-[#14171C] hover:text-[#E6E9ED]'}
            `}
          >
            <span>{item.label}</span>
            {item.badge && (
              <span
                style={{ color: item.badgeColor || '#5C646E' }}
                className="font-mono-code text-[11px]"
              >
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      {/* Daemon & Health Monitor */}
      <div className="border-t border-[#1F242B] mx-0 px-4 pt-3 flex flex-col gap-1.5">
        <div className="flex items-center justify-between font-mono-code text-[11px] text-[#8C949F]">
          <span>Hermes</span>
          <span className="flex items-center gap-1.5 text-[#3FB950]">
            <span className="w-1.5 h-1.5 bg-[#3FB950]" />
            Online
          </span>
        </div>
        <div className="flex items-center justify-between font-mono-code text-[11px] text-[#8C949F]">
          <span>Herdr</span>
          <span className="flex items-center gap-1.5 text-[#3FB950]">
            <span className="w-1.5 h-1.5 bg-[#3FB950]" />
            Online
          </span>
        </div>
        <div className="flex items-center justify-between font-mono-code text-[11px] text-[#8C949F]">
          <span>API</span>
          <span className="flex items-center gap-1.5 text-[#3FB950]">
            <span className="w-1.5 h-1.5 bg-[#3FB950]" />
            Connected
          </span>
        </div>
        <div className="flex items-center justify-between font-mono-code text-[11px] text-[#5C646E] pt-1">
          <span>v0.1.0</span>
          <span>{clock}</span>
        </div>
      </div>
    </aside>
  );
};
