import { LucideIcon } from 'lucide-react';
import { Button } from './Button';

interface SectionAction {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

interface SectionHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: SectionAction[];
  className?: string;
}

export function SectionHeader({
  icon: Icon,
  title,
  subtitle,
  actions = [],
  className = ''
}: SectionHeaderProps) {
  return (
    <div className={`flex items-center justify-between mb-4 ${className}`}>
      <div className="flex items-start gap-2 flex-1">
        <Icon className="w-5 h-5 text-gray-600 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
          {subtitle && (
            <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>

      {actions.length > 0 && (
        <div className="flex gap-2 ml-4">
          {actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant || 'secondary'}
              size={action.size || 'sm'}
              icon={action.icon}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
