import { useState, useMemo, useCallback } from 'react';
import { Plus, X, Server } from 'lucide-react';
import { Input } from './ui/Input';
import { LAYOUT, EMPTY_STATE_MESSAGE } from '../constants/ui';
import type { McpServer } from '../lib/api';

// Local constants
const SERVER_LIST_HEIGHT = LAYOUT.SKILL_LIST_HEIGHT;

interface McpServerSelectorProps {
  availableServers: McpServer[];
  selectedServerIds: string[];
  onAddServer: (serverId: string) => void;
  onRemoveServer: (serverId: string) => void;
  isEditing: boolean;
}

// Extracted Components
interface ServerCardProps {
  server: McpServer;
  onRemove?: (serverId: string) => void;
  showRemoveButton?: boolean;
}

function ServerCard({ server, onRemove, showRemoveButton = true }: ServerCardProps) {
  return (
    <button
      type="button"
      onClick={() => onRemove?.(server.id)}
      className="w-full px-3 py-2 rounded-lg border border-gray-200 bg-white hover:border-red-300 hover:bg-red-50 transition-all text-left group"
      title={`${server.name} - click to remove`}
      aria-label={`Remove ${server.name}`}
    >
      <div className="flex items-center gap-3">
        <Server className="w-4 h-4 text-gray-500 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-900 flex-1 group-hover:text-red-600 transition-colors">
          {server.name}
        </span>
        <X className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  );
}

interface AvailableServerCardProps {
  server: McpServer;
  onAdd: (serverId: string) => void;
}

function AvailableServerCard({ server, onAdd }: AvailableServerCardProps) {
  return (
    <button
      type="button"
      onClick={() => onAdd(server.id)}
      className="w-full px-3 py-3 rounded-lg border border-gray-200 bg-white hover:border-primary-300 hover:bg-primary-50 transition-all text-left"
      aria-label={`Add ${server.name}`}
    >
      <div className="flex items-center gap-3">
        <Server className="w-4 h-4 text-primary-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-gray-900 text-sm mb-0.5">
            {server.name}
          </div>
          <div className="text-xs text-gray-600 line-clamp-2">
            {server.description}
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
export function McpServerSelector({
  availableServers,
  selectedServerIds,
  onAddServer,
  onRemoveServer,
  isEditing,
}: McpServerSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('');

  // Memoized computations
  const validServers = useMemo(
    () => selectedServerIds
      .map((serverId) => availableServers.find((s) => s.id === serverId))
      .filter((server): server is McpServer => server !== undefined),
    [selectedServerIds, availableServers]
  );

  const unselectedServers = useMemo(
    () => availableServers.filter((server) => !selectedServerIds.includes(server.id)),
    [availableServers, selectedServerIds]
  );

  const filteredAvailableServers = useMemo(() => {
    if (!searchQuery) return unselectedServers;
    const query = searchQuery.toLowerCase();
    return unselectedServers.filter(
      (server) =>
        server.name.toLowerCase().includes(query) ||
        server.description.toLowerCase().includes(query) ||
        server.id.toLowerCase().includes(query)
    );
  }, [unselectedServers, searchQuery]);

  // Memoized callbacks
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value),
    []
  );

  // Render helpers
  const renderServersList = useCallback(
    (servers: McpServer[]) => {
      if (servers.length === 0) {
        return (
          <div className="text-sm text-gray-500 text-center py-8">
            No MCP servers added yet
          </div>
        );
      }

      return servers.map((server) => (
        <ServerCard
          key={server.id}
          server={server}
          onRemove={onRemoveServer}
          showRemoveButton
        />
      ));
    },
    [onRemoveServer]
  );

  const renderAvailableServers = useCallback(() => {
    if (filteredAvailableServers.length === 0) {
      const message = searchQuery
        ? EMPTY_STATE_MESSAGE.NO_RESULTS
        : EMPTY_STATE_MESSAGE.ALL_ADDED;
      return <EmptyState message={message} />;
    }

    return filteredAvailableServers.map((server) => (
      <AvailableServerCard key={server.id} server={server} onAdd={onAddServer} />
    ));
  }, [filteredAvailableServers, searchQuery, onAddServer]);

  // Common selected servers panel
  const selectedServersPanel = (
    <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${SERVER_LIST_HEIGHT} overflow-y-auto w-full lg:w-80 flex-shrink-0`}>
      <div className="space-y-2">
        {renderServersList(validServers)}
      </div>
    </div>
  );

  // Read-only view
  if (!isEditing) {
    return (
      <div className="flex flex-col lg:flex-row gap-3">
        {selectedServersPanel}
      </div>
    );
  }

  // Edit mode view
  return (
    <div className="flex flex-col lg:flex-row gap-3">
      {selectedServersPanel}

      {/* Available Servers Panel */}
      <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${SERVER_LIST_HEIGHT} flex flex-col flex-1`}>
        <Input
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder="Search MCP servers to add"
          className="mb-2.5 flex-shrink-0"
          aria-label="Search available MCP servers"
        />

        <div className="space-y-2 flex-1 overflow-y-auto scrollbar-hide">
          {renderAvailableServers()}
        </div>
      </div>
    </div>
  );
}
