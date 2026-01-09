import { useState, useMemo, useCallback } from 'react';
import { Plus, X, FileText, Code, Terminal } from 'lucide-react';
import { Input } from './ui/Input';
import { LAYOUT, EMPTY_STATE_MESSAGE } from '../constants/ui';
import { BUILTIN_TOOLS, type BuiltinTool } from '../constants/builtinTools';

// Local constants
const TOOL_LIST_HEIGHT = LAYOUT.SKILL_LIST_HEIGHT;

interface BuiltinToolSelectorProps {
  selectedToolIds: string[];
  onAddTool: (toolId: string) => void;
  onRemoveTool: (toolId: string) => void;
  isEditing: boolean;
}

// Get icon for tool category
function getCategoryIcon(category: BuiltinTool['category']) {
  switch (category) {
    case 'file':
      return FileText;
    case 'code':
      return Code;
    case 'system':
      return Terminal;
    default:
      return FileText;
  }
}

// Extracted Components
interface ToolCardProps {
  tool: BuiltinTool;
  onRemove?: (toolId: string) => void;
  showRemoveButton?: boolean;
}

function ToolCard({ tool, onRemove, showRemoveButton = true }: ToolCardProps) {
  const IconComponent = getCategoryIcon(tool.category);

  return (
    <button
      type="button"
      onClick={() => onRemove?.(tool.id)}
      className="w-full px-3 py-2 rounded-lg border border-gray-200 bg-white hover:border-red-300 hover:bg-red-50 transition-all text-left group"
      title={`${tool.name} - click to remove`}
      aria-label={`Remove ${tool.name}`}
    >
      <div className="flex items-center gap-3">
        <IconComponent className="w-4 h-4 text-gray-500 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-900 flex-1 group-hover:text-red-600 transition-colors">
          {tool.name}
        </span>
        <X className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  );
}

interface AvailableToolCardProps {
  tool: BuiltinTool;
  onAdd: (toolId: string) => void;
}

function AvailableToolCard({ tool, onAdd }: AvailableToolCardProps) {
  const IconComponent = getCategoryIcon(tool.category);

  return (
    <button
      type="button"
      onClick={() => onAdd(tool.id)}
      className="w-full px-3 py-3 rounded-lg border border-gray-200 bg-white hover:border-primary-300 hover:bg-primary-50 transition-all text-left"
      aria-label={`Add ${tool.name}`}
    >
      <div className="flex items-center gap-3">
        <IconComponent className="w-4 h-4 text-primary-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-gray-900 text-sm mb-0.5">
            {tool.name}
          </div>
          <div className="text-xs text-gray-600 line-clamp-2">
            {tool.description}
          </div>
        </div>
        <div className="flex-shrink-0 opacity-60">
          <Plus className="w-4 h-4 text-primary-600" />
        </div>
      </div>
    </button>
  );
}

interface EmptyStateProps {
  message: string;
}

function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="text-sm text-gray-500 text-center py-8">
      {message}
    </div>
  );
}

// Main Component
export function BuiltinToolSelector({
  selectedToolIds,
  onAddTool,
  onRemoveTool,
  isEditing,
}: BuiltinToolSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('');

  // Memoized computations
  const validTools = useMemo(
    () => selectedToolIds
      .map((toolId) => BUILTIN_TOOLS.find((t) => t.id === toolId))
      .filter((tool): tool is BuiltinTool => tool !== undefined),
    [selectedToolIds]
  );

  const unselectedTools = useMemo(
    () => BUILTIN_TOOLS.filter((tool) => !selectedToolIds.includes(tool.id)),
    [selectedToolIds]
  );

  const filteredAvailableTools = useMemo(() => {
    if (!searchQuery) return unselectedTools;
    const query = searchQuery.toLowerCase();
    return unselectedTools.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        tool.description.toLowerCase().includes(query) ||
        tool.category.toLowerCase().includes(query)
    );
  }, [unselectedTools, searchQuery]);

  // Memoized callbacks
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value),
    []
  );

  // Render helpers
  const renderToolsList = useCallback(
    (tools: BuiltinTool[]) => {
      if (tools.length === 0) {
        return (
          <div className="text-sm text-gray-500 text-center py-8">
            No tools added yet
          </div>
        );
      }

      return tools.map((tool) => (
        <ToolCard
          key={tool.id}
          tool={tool}
          onRemove={onRemoveTool}
          showRemoveButton
        />
      ));
    },
    [onRemoveTool]
  );

  const renderAvailableTools = useCallback(() => {
    if (filteredAvailableTools.length === 0) {
      const message = searchQuery
        ? EMPTY_STATE_MESSAGE.NO_RESULTS
        : EMPTY_STATE_MESSAGE.ALL_ADDED;
      return <EmptyState message={message} />;
    }

    return filteredAvailableTools.map((tool) => (
      <AvailableToolCard key={tool.id} tool={tool} onAdd={onAddTool} />
    ));
  }, [filteredAvailableTools, searchQuery, onAddTool]);

  // Common selected tools panel
  const selectedToolsPanel = (
    <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${TOOL_LIST_HEIGHT} overflow-y-auto w-80 flex-shrink-0`}>
      <div className="space-y-2">
        {renderToolsList(validTools)}
      </div>
    </div>
  );

  // Read-only view
  if (!isEditing) {
    return (
      <div className="flex gap-3">
        {selectedToolsPanel}
      </div>
    );
  }

  // Edit mode view
  return (
    <div className="flex gap-3">
      {selectedToolsPanel}

      {/* Available Tools Panel */}
      <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${TOOL_LIST_HEIGHT} flex flex-col flex-1`}>
        <Input
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder="Search built-in tools to add"
          className="mb-2.5 flex-shrink-0"
          aria-label="Search available built-in tools"
        />

        <div className="space-y-2 flex-1 overflow-y-auto scrollbar-hide">
          {renderAvailableTools()}
        </div>
      </div>
    </div>
  );
}
