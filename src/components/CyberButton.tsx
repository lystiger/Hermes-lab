import React from 'react';

interface CyberButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  active?: boolean;
}

export const CyberButton: React.FC<CyberButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  active = false,
  className = '',
  ...props
}) => {
  const baseClasses = "inline-flex items-center justify-center font-mono-code transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none";
  
  const sizeClasses = {
    sm: 'text-[11px] px-2 py-0.5',
    md: 'text-[12px] px-3 py-1',
    lg: 'text-[13px] px-4 py-2'
  }[size];

  const variantClasses = {
    primary: 'bg-[#CBA35C] text-[#0A0B0D] font-semibold hover:bg-[#E8CE9B] border border-[#CBA35C]',
    secondary: 'bg-[#12151A] text-[#E6E9ED] border border-[#2A3038] hover:border-[#5C646E] hover:bg-[#161A20]',
    ghost: 'bg-transparent text-[#8C949F] hover:text-[#E6E9ED] border border-transparent hover:border-[#2A3038]',
    danger: 'bg-[rgba(242,85,90,0.1)] text-[#F2555A] border border-[rgba(242,85,90,0.4)] hover:bg-[rgba(242,85,90,0.2)]'
  }[variant];

  const activeClasses = active ? 'border-[#CBA35C] text-[#E6E9ED] bg-[#1F242B]' : '';

  return (
    <button
      className={`${baseClasses} ${sizeClasses} ${variantClasses} ${activeClasses} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};
