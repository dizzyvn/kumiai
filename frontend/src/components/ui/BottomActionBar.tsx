import { Button } from './Button';

interface ActionButton {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  disabled?: boolean;
}

interface BottomActionBarProps {
  primaryAction: ActionButton;
  secondaryActions?: ActionButton[];
  customContent?: React.ReactNode;
  className?: string;
}

export function BottomActionBar({
  primaryAction,
  secondaryActions = [],
  customContent,
  className = ''
}: BottomActionBarProps) {
  return (
    <div className={`flex-shrink-0 border-t border-gray-200 bg-white p-4 space-y-3 ${className}`}>
      <Button
        variant={primaryAction.variant || 'primary'}
        size="md"
        icon={primaryAction.icon}
        onClick={primaryAction.onClick}
        disabled={primaryAction.disabled}
        className="w-full"
      >
        {primaryAction.label}
      </Button>

      {secondaryActions.map((action, index) => (
        <Button
          key={index}
          variant={action.variant || 'secondary'}
          size="md"
          icon={action.icon}
          onClick={action.onClick}
          disabled={action.disabled}
          className="w-full"
        >
          {action.label}
        </Button>
      ))}

      {customContent}
    </div>
  );
}
