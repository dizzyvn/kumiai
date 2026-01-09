import { layout } from '@/styles/design-system';
import { SearchBar } from './SearchBar';
import { BottomActionBar } from './BottomActionBar';
import { EmptyState } from './EmptyState';
import { LucideIcon } from 'lucide-react';

interface ActionButton {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
}

interface SidebarProps {
  // Search
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  showSearch?: boolean;

  // Content
  children: React.ReactNode;
  isLoading?: boolean;
  isEmpty?: boolean;
  emptyIcon?: LucideIcon;
  emptyTitle?: string;
  emptyDescription?: string;

  // Bottom actions
  primaryAction?: ActionButton;
  secondaryActions?: ActionButton[];
  bottomContent?: React.ReactNode;

  // Styling
  className?: string;
  width?: string;
}

export function Sidebar({
  searchValue = '',
  onSearchChange,
  searchPlaceholder = 'Search...',
  showSearch = true,
  children,
  isLoading = false,
  isEmpty = false,
  emptyIcon,
  emptyTitle = 'No items',
  emptyDescription,
  primaryAction,
  secondaryActions = [],
  bottomContent,
  className = '',
  width = layout.sidebarWidth
}: SidebarProps) {
  const showEmptyState = (isLoading || isEmpty) && emptyIcon;

  return (
    <div
      className={`border-r border-gray-200 flex flex-col relative ${className}`}
      style={{ width }}
    >
      {/* Search Bar */}
      {showSearch && onSearchChange && (
        <SearchBar
          value={searchValue}
          onChange={onSearchChange}
          placeholder={searchPlaceholder}
        />
      )}

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-2">
        {showEmptyState && emptyIcon ? (
          <EmptyState
            icon={emptyIcon}
            title={emptyTitle}
            description={emptyDescription}
            isLoading={isLoading}
          />
        ) : (
          children
        )}
      </div>

      {/* Bottom Action Bar */}
      {primaryAction && (
        <BottomActionBar
          primaryAction={primaryAction}
          secondaryActions={secondaryActions}
          customContent={bottomContent}
        />
      )}
    </div>
  );
}
