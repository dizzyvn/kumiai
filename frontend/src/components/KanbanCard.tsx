import { useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { AgentInstance, AgentCharacter } from '@/lib/api';
import { Moon, Loader2, Settings, MessageCircle, CheckCircle, XCircle, Trash2 } from 'lucide-react';
import { Avatar } from './Avatar';
import { BUILT_IN_AGENTS } from '@/constants/ui';

interface KanbanCardProps {
  agent: AgentInstance;
  characters: AgentCharacter[];
  onClick: () => void;
  onDelete?: (agentId: string) => void;
}

const statusIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  idle: Moon,
  thinking: Loader2,
  working: Settings,
  waiting: MessageCircle,
  completed: CheckCircle,
  error: XCircle,
} as const;

export function KanbanCard({ agent, characters, onClick, onDelete }: KanbanCardProps) {
  const StatusIcon = statusIcons[agent.status] || Settings;

  // Memoize team members calculation
  const teamMembers = useMemo(() => {
    const selectedIds = agent.selected_specialists || [];
    return selectedIds
      .map(id => characters.find(c => c.id === id))
      .filter((c): c is AgentCharacter => c !== undefined);
  }, [agent.selected_specialists, characters]);

  // Memoized delete handler
  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete) {
      onDelete(agent.instance_id);
    }
  }, [onDelete, agent.instance_id]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      whileHover={{ scale: 1.02 }}
      onClick={onClick}
      className={cn(
        'group relative p-2 rounded-lg border-2 cursor-pointer transition-all bg-white',
        'hover:shadow-md border-gray-200 hover:border-gray-300'
      )}
      role="button"
      aria-label={`Session for ${teamMembers.map(m => m.name).join(', ') || agent.character.name}, status: ${agent.status}`}
    >
      {/* Delete Button */}
      {onDelete && (
        <button
          onClick={handleDelete}
          className="absolute top-2 right-2 p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100"
          title="Delete session"
          aria-label="Delete session"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}

      {/* Team Avatars - Compact horizontal layout */}
      <div className="flex items-center gap-2 mb-2">
        {teamMembers.slice(0, 3).map((character) => (
          <Avatar
            key={character.id}
            seed={character.avatar}
            size={28}
            className="w-7 h-7"
            color={character.color}
          />
        ))}
        {teamMembers.length > 3 && (
          <div
            className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-[10px] font-medium text-gray-600"
            aria-label={`${teamMembers.length - 3} more team members`}
          >
            +{teamMembers.length - 3}
          </div>
        )}
      </div>

      {/* Session */}
      {agent.current_session_description && (
        <p className="text-sm text-gray-700 line-clamp-2 mb-2 font-medium">
          {agent.current_session_description}
        </p>
      )}

      {/* Status Badge */}
      <div className="flex items-center gap-1.5">
        <StatusIcon
          className={cn(
            "w-4 h-4",
            agent.status === 'thinking' && "animate-spin",
            agent.status === 'working' && "animate-spin"
          )}
          style={{ color: agent.character.color }}
        />
        <span
          className="text-xs font-medium px-1.5 py-0.5 rounded capitalize"
          style={{
            backgroundColor: agent.character.color + '20',
            color: agent.character.color,
          }}
        >
          {agent.status}
        </span>
      </div>
    </motion.div>
  );
}
