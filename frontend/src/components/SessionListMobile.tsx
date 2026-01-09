import { AgentInstance, CharacterMetadata } from '@/lib/api';
import { Avatar } from './Avatar';
import { Button } from './ui/Button';
import { cn } from '@/lib/utils';
import { Moon, Loader2, Settings, MessageCircle, CheckCircle, XCircle, Trash2, Plus, ChevronRight } from 'lucide-react';

interface SessionListMobileProps {
  sessions: AgentInstance[];
  characters: CharacterMetadata[];
  onSessionSelect: (session: AgentInstance) => void;
  onSessionDelete?: (sessionId: string) => void;
  onSessionCreate?: () => void;
  selectedSessionId?: string;
  onBack?: () => void;
  loading?: boolean;
}

const statusIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  idle: Moon,
  thinking: Loader2,
  working: Settings,
  waiting: MessageCircle,
  completed: CheckCircle,
  error: XCircle,
} as const;

// Get stage badge color
function getStageColor(stage: string) {
  switch (stage) {
    case 'active':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    case 'waiting':
      return 'bg-yellow-50 text-yellow-700 border-yellow-200';
    case 'done':
      return 'bg-green-50 text-green-700 border-green-200';
    default:
      return 'bg-gray-50 text-gray-700 border-gray-200';
  }
}

export function SessionListMobile({
  sessions,
  characters,
  onSessionSelect,
  onSessionDelete,
  onSessionCreate,
  selectedSessionId,
  onBack,
  loading = false
}: SessionListMobileProps) {
  // Group sessions by stage
  const sessionsByStage = sessions.reduce((acc, session) => {
    const stage = session.kanban_stage || 'backlog';
    if (!acc[stage]) acc[stage] = [];
    acc[stage].push(session);
    return acc;
  }, {} as Record<string, AgentInstance[]>);

  const stages = [
    { id: 'backlog', label: 'Backlog' },
    { id: 'active', label: 'Active' },
    { id: 'waiting', label: 'Waiting' },
    { id: 'done', label: 'Done' },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      {/* Back to Projects Header */}
      {onBack && (
        <div className="flex-shrink-0 border-b border-gray-200 bg-white px-4 py-3">
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-gray-700 hover:text-gray-900 transition-colors"
          >
            <ChevronRight className="w-5 h-5 rotate-180" />
            <span className="font-medium">Back to Projects</span>
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto overscroll-contain">
      {stages.map((stage) => {
        const stageSessions = sessionsByStage[stage.id] || [];
        if (stageSessions.length === 0) return null;

        return (
          <div key={stage.id} className="mb-4">
            {/* Stage Header */}
            <div className="sticky top-0 bg-gray-100 px-4 py-2 border-b border-gray-200 z-10">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">
                  {stage.label}
                </h3>
                <span className="text-xs text-gray-500 bg-white px-2 py-1 rounded-full">
                  {stageSessions.length}
                </span>
              </div>
            </div>

            {/* Sessions List */}
            <div className="px-4 py-2 space-y-2">
              {stageSessions.map((session) => {
                const character = characters.find(c => c.id === session.character_id);
                const isSelected = session.instance_id === selectedSessionId;
                const StatusIcon = statusIcons[session.status] || Settings;

                // Get team members (selected specialists)
                const teamMembers = (session.selected_specialists || [])
                  .map(id => characters.find(c => c.id === id))
                  .filter((c): c is CharacterMetadata => c !== undefined);

                return (
                  <div
                    key={session.instance_id}
                    onClick={() => onSessionSelect(session)}
                    className={cn(
                      'group relative p-2 rounded-lg border-2 cursor-pointer transition-all bg-white',
                      isSelected
                        ? 'border-primary-600 shadow-md'
                        : 'border-gray-200 hover:border-gray-300 hover:shadow-md'
                    )}
                  >
                    {/* Delete Button */}
                    {onSessionDelete && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm('Delete this session?')) {
                            onSessionDelete(session.instance_id);
                          }
                        }}
                        className="absolute top-2 right-2 p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete session"
                        aria-label="Delete session"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}

                    {/* Team Avatars - Compact horizontal layout */}
                    <div className="flex items-center gap-2 mb-2">
                      {teamMembers.slice(0, 3).map((char) => (
                        <Avatar
                          key={char.id}
                          seed={char.avatar || char.id}
                          size={28}
                          className="w-7 h-7"
                          color={char.color}
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

                    {/* Session Description */}
                    {session.current_session_description && (
                      <p className="text-sm text-gray-700 line-clamp-2 mb-2 font-medium">
                        {session.current_session_description}
                      </p>
                    )}

                    {/* Status Badge */}
                    <div className="flex items-center gap-1.5">
                      <StatusIcon
                        className={cn(
                          "w-4 h-4",
                          session.status === 'thinking' && "animate-spin",
                          session.status === 'working' && "animate-spin"
                        )}
                        style={{ color: character?.color }}
                      />
                      <span
                        className="text-xs font-medium px-1.5 py-0.5 rounded capitalize"
                        style={{
                          backgroundColor: character?.color ? character.color + '20' : '#f9f9f9',
                          color: character?.color || '#99999b',
                        }}
                      >
                        {session.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {sessions.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          {loading ? (
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
              <p className="text-gray-500">Loading sessions...</p>
            </div>
          ) : (
            <div className="text-center text-gray-500">
              <p className="text-sm">No sessions yet</p>
              <p className="text-xs text-gray-400 mt-1">Create one to get started</p>
            </div>
          )}
        </div>
      )}
      </div>

      {/* Bottom Action Container */}
      {onSessionCreate && (
        <div className="flex-shrink-0 bg-white p-4">
          <Button
            variant="primary"
            size="md"
            icon={<Plus className="w-5 h-5" />}
            onClick={onSessionCreate}
            className="w-full"
          >
            New Session
          </Button>
        </div>
      )}
    </div>
  );
}
