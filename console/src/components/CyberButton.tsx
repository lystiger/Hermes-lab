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
  const baseClasses = "inline-flex items-center justify-center font-sans transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none";
  
  const sizeClasses = {
    sm: 'text-[11px] px-2 py-0.5',
    md: 'text-[12px] px-3 py-1',
    lg: 'text-[13px] px-4 py-2'
  }[size];

  const variantClasses = {
    primary: 'bg-lys-gold text-lys-base font-semibold hover:bg-lys-gold-hover border border-lys-gold',
    secondary: 'bg-lys-surface-1 text-lys-primary border border-lys-default hover:border-lys-strong hover:bg-lys-surface-2',
    ghost: 'bg-transparent text-lys-muted hover:text-lys-primary border border-transparent hover:border-lys-default',
    danger: 'bg-lys-danger/10 text-lys-danger border border-lys-danger/40 hover:bg-lys-danger/20'
  }[variant];

  const activeClasses = active ? 'border-lys-gold text-lys-primary bg-lys-surface-interactive' : '';

  return (
    <button
      className={`${baseClasses} ${sizeClasses} ${variantClasses} ${activeClasses} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};
