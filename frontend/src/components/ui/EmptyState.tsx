import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  isLoading?: boolean;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  isLoading = false,
  className = ''
}: EmptyStateProps) {
  return (
    <div className={`p-6 text-center text-gray-500 ${className}`}>
      <Icon
        className={`w-12 h-12 mx-auto mb-2.5 text-gray-400 ${isLoading ? 'animate-pulse' : ''}`}
      />
      <p className="text-sm">{title}</p>
      {description && (
        <p className="text-xs text-gray-400 mt-1">{description}</p>
      )}
    </div>
  );
}
