import { useState, useRef, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { AgentInstance, CharacterMetadata } from '@/lib/api';
import {
  Moon, Loader2, Settings, MessageCircle, CheckCircle, XCircle
} from 'lucide-react';
import { Avatar } from './Avatar';
import { AgentTooltip } from './AgentTooltip';
import { BUILT_IN_AGENTS } from '@/constants/ui';

interface AgentCardProps {
  agent: AgentInstance;
  characters: CharacterMetadata[];
  isSelected: boolean;
  onClick: () => void;
}

const statusIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  idle: Moon,
  thinking: Loader2,
  working: Settings,
  waiting: MessageCircle,
  completed: CheckCircle,
  error: XCircle,
} as const;

export function AgentCard({ agent, characters, isSelected, onClick }: AgentCardProps) {
  const StatusIcon = statusIcons[agent.status] || Settings;
  const [hoveredCharacter, setHoveredCharacter] = useState<CharacterMetadata | null>(null);
  const hoveredRef = useRef<HTMLDivElement>(null);

  // Memoize team members calculation
  const teamMembers = useMemo(() => {
    const selectedIds = agent.selected_specialists || [];
    return selectedIds
      .map(id => characters.find(c => c.id === id))
      .filter((c): c is CharacterMetadata => c !== undefined);
  }, [agent.selected_specialists, characters]);

  // Memoized callbacks
  const handleMouseEnter = useCallback((character: CharacterMetadata) => {
    setHoveredCharacter(character);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHoveredCharacter(null);
  }, []);

  return (
    <motion.div
      className={cn(
        'relative p-4 rounded-xl border-2 cursor-pointer overflow-visible',
        'transition-all duration-200 bg-white',
        isSelected ? 'shadow-lg scale-[1.02] border-primary-500' : 'border-gray-200 hover:scale-[1.01] hover:border-gray-300'
      )}
      onClick={onClick}
      whileHover={{ y: -2 }}
      style={{ zIndex: isSelected ? 10 : 1 }}
      role="button"
      aria-pressed={isSelected}
      aria-label={`Agent ${agent.character.name}, status: ${agent.status}`}
    >
      {/* Team Avatars - Show all team members side by side */}
      <div className="mb-2.5 pb-3 border-b border-gray-200">
        <div className="flex items-center gap-3">
          {teamMembers.slice(0, 5).map((character) => (
            <div
              key={character.id}
              ref={hoveredCharacter?.id === character.id ? hoveredRef : null}
              className="text-center"
              onMouseEnter={() => handleMouseEnter(character)}
              onMouseLeave={handleMouseLeave}
            >
              <Avatar
                seed={character.avatar}
                size={40}
                className="w-10 h-10 mx-auto"
                color={character.color}
              />
              <div className="text-xs font-medium text-gray-700 mt-1 truncate max-w-[60px]">
                {character.name}
              </div>
            </div>
          ))}
          {hoveredCharacter && <AgentTooltip character={hoveredCharacter} targetRef={hoveredRef} />}
          {teamMembers.length > 5 && (
            <div className="text-center">
              <div
                className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-600"
                aria-label={`${teamMembers.length - 5} more team members`}
              >
                +{teamMembers.length - 5}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2 mb-3">
        <StatusIcon className={cn(
          "w-5 h-5",
          agent.status === 'thinking' && "animate-spin",
          agent.status === 'working' && "animate-spin"
        )} style={{ color: agent.character.color }} />
        <span
          className="text-xs font-medium px-2 py-1 rounded capitalize"
          style={{
            backgroundColor: agent.character.color + '20',
            color: agent.character.color,
          }}
        >
          {agent.status}
        </span>
      </div>

      {/* Current Session */}
      {agent.current_session_description && (
        <div className="text-xs text-gray-600 line-clamp-2">
          <span className="font-medium">Session:</span> {agent.current_session_description}
        </div>
      )}

      {/* Activity Indicator */}
      {agent.status === 'working' && (
        <motion.div
          className="absolute top-2 right-2 w-3 h-3 rounded-full"
          style={{ backgroundColor: agent.character.color }}
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
          aria-label="Agent is working"
        />
      )}
    </motion.div>
  );
}
