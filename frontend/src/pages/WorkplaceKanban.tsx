import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Search, FolderOpen, Trash2, ChevronLeft, ChevronRight, Pencil, Loader2 } from 'lucide-react';
import { api, type CharacterMetadata, type AgentInstance, type Project } from '../lib/api';
import { KanbanCard } from '../components/KanbanCard';
import { UnifiedChatSessionModal } from '../components/UnifiedChatSessionModal';
import { PMChat } from '../components/PMChat';
import { Avatar } from '../components/Avatar';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { FileViewerModal } from '../components/FileViewerModal';
import { SessionListMobile } from '../components/SessionListMobile';
import { MobileHeader } from '../components/MobileHeader';
import { cn, layout } from '../styles/design-system';
import { getSkillIcon } from '../constants/skillIcons';
import type { ChatContext } from '@/types/chat';
import { paths } from '@/lib/config';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  useDroppable,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// Workflow stage column configuration
const COLUMNS = [
  { id: 'backlog', label: 'Backlog', color: 'bg-gray-50' },
  { id: 'active', label: 'Active', color: 'bg-primary-50' },
  { id: 'waiting', label: 'Waiting', color: 'bg-gray-100' },
  { id: 'done', label: 'Done', color: 'bg-accent-50' },
] as const;

type ColumnId = typeof COLUMNS[number]['id'];

// Draggable card wrapper
function DraggableCard({
  agent,
  characters,
  onClick,
  onDelete
}: {
  agent: AgentInstance;
  characters: CharacterMetadata[];
  onClick: () => void;
  onDelete?: (agentId: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: agent.instance_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <KanbanCard agent={agent} characters={characters} onClick={onClick} onDelete={onDelete} />
    </div>
  );
}

interface WorkplaceKanbanProps {
  onChatContextChange?: (context: ChatContext) => void;
  currentProjectId?: string;
  onProjectChange?: (projectId: string) => void;
}

export default function WorkplaceKanban({ onChatContextChange, currentProjectId, onProjectChange }: WorkplaceKanbanProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [characters, setCharacters] = useState<CharacterMetadata[]>([]);
  const [agents, setAgents] = useState<AgentInstance[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<AgentInstance | null>(null);
  const [showSpawnDialog, setShowSpawnDialog] = useState(false);
  const [spawnDialogInitialStage, setSpawnDialogInitialStage] = useState<string>('backlog');
  const [showCreateProjectDialog, setShowCreateProjectDialog] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Project management state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  // Get session ID from URL
  const sessionIdFromUrl = searchParams.get('session');

  // File explorer state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'kanban' | 'chat' | 'file'>('kanban');

  // PM chat open state
  const [isPMChatOpen, setIsPMChatOpen] = useState(() => {
    const saved = localStorage.getItem('isPMChatOpen');
    return saved ? JSON.parse(saved) : false;
  });


  // Save PM chat open state to localStorage
  useEffect(() => {
    localStorage.setItem('isPMChatOpen', JSON.stringify(isPMChatOpen));
  }, [isPMChatOpen]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  useEffect(() => {
    api.getCharactersLibrary().then(chars => {
      console.log('[FRONTEND] Loaded characters:', chars);
      setCharacters(chars);
    });
    api.getSessions().then(sessions => {
      console.log('[FRONTEND] Loaded sessions:', sessions);
      setAgents(sessions);
      setSessionsLoading(false);
    }).catch(error => {
      console.error('[FRONTEND] Failed to load sessions:', error);
      setSessionsLoading(false);
    });

    // Load projects from API
    api.getProjects().then(fetchedProjects => {
      console.log('[FRONTEND] Loaded projects:', fetchedProjects);
      setProjects(fetchedProjects);
      // Auto-select based on currentProjectId or first project
      if (fetchedProjects.length > 0) {
        const projectToSelect = currentProjectId
          ? fetchedProjects.find(p => p.id === currentProjectId) || fetchedProjects[0]
          : fetchedProjects[0];
        setSelectedProject(projectToSelect);
      }
      setProjectsLoading(false);
    }).catch(error => {
      console.error('[FRONTEND] Failed to load projects:', error);
      setProjectsLoading(false);
    });

    // Poll for task updates
    const interval = setInterval(() => {
      api.getSessions().then(sessions => {
        setAgents(sessions);
      });
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  // Update selectedProject when currentProjectId prop changes
  useEffect(() => {
    if (currentProjectId && projects.length > 0) {
      const project = projects.find(p => p.id === currentProjectId);
      if (project && project.id !== selectedProject?.id) {
        setSelectedProject(project);
      }
    }
  }, [currentProjectId, projects]);

  // Sync selectedAgent with updated agent data from polling
  useEffect(() => {
    if (selectedAgent) {
      const updatedAgent = agents.find(a => a.instance_id === selectedAgent.instance_id);
      if (updatedAgent) {
        setSelectedAgent(updatedAgent);
      }
    }
  }, [agents]);

  // Restore selected session from URL on mount or when agents load
  useEffect(() => {
    if (sessionIdFromUrl && agents.length > 0 && !selectedAgent) {
      const sessionToRestore = agents.find(a => a.instance_id === sessionIdFromUrl);
      if (sessionToRestore) {
        setSelectedAgent(sessionToRestore);
        setViewMode('chat');
      }
    }
  }, [sessionIdFromUrl, agents]);

  // Update URL when session selection changes
  const updateSessionInUrl = (sessionId: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (sessionId) {
      params.set('session', sessionId);
    } else {
      params.delete('session');
    }
    if (currentProjectId) {
      params.set('project', currentProjectId);
    }
    setSearchParams(params, { replace: true });
  };

  // Detect PM session and set chat context
  useEffect(() => {
    if (!onChatContextChange || !selectedProject) {
      return;
    }

    // Find PM session for the selected project
    const pmSession = agents.find(agent =>
      agent.role === 'pm' &&
      agent.project_id === selectedProject.id
    );

    if (pmSession) {
      // PM exists for this project - set context
      console.log('[PM Detection] Setting PM context for project:', selectedProject.name, 'PM instance:', pmSession.instance_id);
      onChatContextChange({
        role: 'pm',
        name: `PM for ${selectedProject.name}`,
        description: `Project Manager for ${selectedProject.name}. The PM coordinates multi-agent workflows, spawns orchestrator sessions, manages project status, and tracks progress through the kanban board.`,
        data: {
          project_path: selectedProject.path,
          project_id: selectedProject.id,
          pm_session_id: pmSession.instance_id,
        },
      });
    } else {
      // No PM session found - should have been auto-created when project was created
      console.warn('[PM Detection] No PM found for project:', selectedProject.name);
      console.warn('[PM Detection] PM sessions are now auto-created when projects are created. This project may be old.');
      // Clear context
      onChatContextChange({
        role: null,
      });
    }
  }, [agents, selectedProject, onChatContextChange]);

  // Filter agents by selected project (exclude PM sessions)
  const projectAgents = selectedProject
    ? agents.filter(agent =>
        agent.project_id === selectedProject.id &&
        agent.role !== 'pm'  // Filter out PM sessions - they appear in sidebar
      )
    : [];

  // Group agents by kanban stage (default to 'backlog' if not set)
  const agentsByStage = COLUMNS.reduce((acc, col) => {
    acc[col.id] = projectAgents.filter(a => (a.kanban_stage || 'backlog') === col.id);
    return acc;
  }, {} as Record<ColumnId, AgentInstance[]>);

  const handleDragStart = (event: any) => {
    setActiveId(event.active.id);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    // Check if dropped on a column
    const overId = over.id as string;
    const targetColumn = COLUMNS.find(col => col.id === overId);

    if (targetColumn && active.id !== targetColumn.id) {
      try {
        // Optimistically update UI
        setAgents(prev => prev.map(a =>
          a.instance_id === active.id
            ? { ...a, kanban_stage: targetColumn.id as any }
            : a
        ));

        // Call backend to persist the change
        await api.updateSessionStage(active.id as string, targetColumn.id);
      } catch (error) {
        console.error('Failed to update session stage:', error);
        // Revert on error
        api.getSessions().then(setAgents);
      }
    }
  };

  const handleDragCancel = () => {
    setActiveId(null);
  };

  const handleDelete = async (agentId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) {
      return;
    }

    try {
      await api.deleteSession(agentId);
      // Remove from local state
      setAgents(prev => prev.filter(a => a.instance_id !== agentId));
      // Close modal if this agent is selected
      if (selectedAgent?.instance_id === agentId) {
        setSelectedAgent(null);
      }
    } catch (error) {
      console.error('Failed to delete agent:', error);
      alert('Failed to delete session. Please try again.');
    }
  };

  const handleDeleteProject = async (projectId: string, projectName: string) => {
    if (!confirm(`Are you sure you want to delete project "${projectName}"?\n\nThis will delete all sessions associated with this project.`)) {
      return;
    }

    try {
      // First, delete all sessions for this project
      const projectSessions = agents.filter(a => a.project_id === projectId);
      await Promise.all(
        projectSessions.map(session => api.deleteSession(session.instance_id))
      );

      // Then delete the project itself
      await api.deleteProject(projectId);

      // Update local state
      setAgents(prev => prev.filter(a => a.project_id !== projectId));
      setProjects(prev => prev.filter(p => p.id !== projectId));

      // Clear selection if this project was selected
      if (selectedProject?.id === projectId) {
        setSelectedProject(projects.find(p => p.id !== projectId) || null);
      }
    } catch (error) {
      console.error('Failed to delete project:', error);
      alert('Failed to delete project. Please try again.');
    }
  };

  const activeAgent = activeId ? agents.find(a => a.instance_id === activeId) : null;

  return (
    <div className="flex-1 flex overflow-hidden bg-white relative">


      {/* Right: Kanban Board or Chat Session */}
      <div className="flex-1 flex flex-col bg-gray-50 overflow-hidden max-w-full border-r-2 border-primary-500">
        {viewMode === 'chat' && selectedAgent ? (
          // Show chat session inline
          <div className="flex-1 overflow-hidden">
            <UnifiedChatSessionModal
              agent={selectedAgent}
              characters={characters}
              onClose={() => {
                setSelectedAgent(null);
                setViewMode('kanban');
                updateSessionInUrl(null);
              }}
              inline={true}
            />
          </div>
        ) : projectsLoading && currentProjectId ? (
          // Loading project
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
              <p className="text-gray-500">Loading project...</p>
            </div>
          </div>
        ) : selectedProject && viewMode === 'kanban' ? (
          <>
            {/* Mobile: Session List View */}
            <div className="flex-1 lg:hidden overflow-hidden">
              <SessionListMobile
                sessions={projectAgents}
                characters={characters}
                selectedSessionId={selectedAgent?.instance_id}
                onSessionSelect={(agent) => {
                  setSelectedAgent(agent);
                  setViewMode('chat');
                  updateSessionInUrl(agent.instance_id);
                }}
                onSessionDelete={handleDelete}
                onSessionCreate={() => {
                  setSpawnDialogInitialStage('backlog');
                  setShowSpawnDialog(true);
                }}
                onBack={() => navigate('/projects')}
                loading={sessionsLoading}
              />
            </div>

            {/* Desktop: Kanban Board */}
            <div className="hidden lg:block flex-1 overflow-x-auto overflow-y-hidden pl-6 pt-6 pb-6">
              <DndContext
                sensors={sensors}
                collisionDetection={pointerWithin}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
                onDragCancel={handleDragCancel}
              >
                <div className="flex gap-4 h-full w-full pr-6">
                  {COLUMNS.map((column, index) => (
                    <KanbanColumn
                      key={column.id}
                      column={column}
                      agents={agentsByStage[column.id]}
                      characters={characters}
                      onCardClick={(agent) => {
                        setSelectedAgent(agent);
                        setViewMode('chat');
                        updateSessionInUrl(agent.instance_id);
                      }}
                      onAddClick={() => {
                        setSpawnDialogInitialStage(column.id);
                        setShowSpawnDialog(true);
                      }}
                      onDeleteCard={handleDelete}
                      isLast={index === COLUMNS.length - 1}
                    />
                  ))}
                </div>

                <DragOverlay>
                  {activeAgent ? (
                    <div className="opacity-80">
                      <KanbanCard
                        agent={activeAgent}
                        characters={characters}
                        onClick={() => {}}
                      />
                    </div>
                  ) : null}
                </DragOverlay>
              </DndContext>
            </div>
          </>
        ) : projectsLoading ? (
          // Loading initial projects
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
              <p className="text-gray-500">Loading...</p>
            </div>
          </div>
        ) : (
          // No project selected
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="text-center text-gray-500">
              <FolderOpen className="w-8 h-8 mx-auto mb-4 text-gray-400" />
              <p className="text-lg font-medium">No project selected</p>
              <p className="text-sm text-gray-400 mt-1">Use Cmd/Ctrl + P to select a project</p>
            </div>
          </div>
        )}
      </div>

      {/* PM Chat - Desktop only */}
      {selectedProject && (
        <div className="hidden lg:block">
          <PMChat
            isOpen={isPMChatOpen}
            onToggle={() => setIsPMChatOpen(!isPMChatOpen)}
            projectId={selectedProject.id}
            projectPath={selectedProject.path}
            projectName={selectedProject.name}
            onSessionJump={(sessionId) => {
              // Find the session in agents list
              const targetAgent = agents.find(a => a.instance_id === sessionId);
              if (targetAgent) {
                setSelectedAgent(targetAgent);
                setViewMode('chat');
                updateSessionInUrl(sessionId);
              } else {
                console.warn(`[WorkplaceKanban] Session ${sessionId} not found in agents list`);
              }
            }}
          />
        </div>
      )}

      {/* Modals - Positioned absolutely, outside flex layout */}
      <AnimatePresence>
        {showSpawnDialog && (
          <SpawnDialog
            characters={characters}
            selectedProject={selectedProject}
            initialStage={spawnDialogInitialStage}
            onClose={() => setShowSpawnDialog(false)}
            onSpawn={(agent) => {
              setAgents([...agents, agent]);
              // Auto-open if created in active stage
              if (agent.kanban_stage === 'active') {
                setSelectedAgent(agent);
                setViewMode('chat');
                updateSessionInUrl(agent.instance_id);
              }
              setShowSpawnDialog(false);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showCreateProjectDialog && (
          <CreateProjectDialog
            onClose={() => setShowCreateProjectDialog(false)}
            onCreate={(project) => {
              setProjects([...projects, project]);
              setSelectedProject(project);
              setShowCreateProjectDialog(false);
              // Update URL to open the new project
              if (onProjectChange) {
                onProjectChange(project.id);
              }
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {editingProject && (
          <CreateProjectDialog
            project={editingProject}
            onClose={() => setEditingProject(null)}
            onCreate={(updatedProject) => {
              setProjects(projects.map(p => p.id === updatedProject.id ? updatedProject : p));
              if (selectedProject?.id === updatedProject.id) {
                setSelectedProject(updatedProject);
              }
              setEditingProject(null);
            }}
          />
        )}
      </AnimatePresence>

      {/* File Viewer Modal */}
      <FileViewerModal
        mode={selectedAgent ? 'session' : 'project'}
        projectId={selectedProject?.id}
        sessionId={selectedAgent?.instance_id}
        filePath={selectedFile}
        onClose={() => setSelectedFile(null)}
      />
    </div>
  );
}

// Kanban Column Component
function KanbanColumn({
  column,
  agents,
  characters,
  onCardClick,
  onAddClick,
  onDeleteCard,
  isLast,
}: {
  column: typeof COLUMNS[number];
  agents: AgentInstance[];
  characters: CharacterMetadata[];
  onCardClick: (agent: AgentInstance) => void;
  onAddClick: () => void;
  onDeleteCard?: (agentId: string) => void;
  isLast?: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col flex-1 min-w-[320px] bg-white rounded-lg border-2 shadow-sm transition-all",
        isOver ? "border-primary-500 bg-primary-50" : "border-gray-200",
        isLast && "mr-6"
      )}
    >
      {/* Column Header */}
      <div className={`p-3 rounded-t-lg border-b border-gray-200 ${column.color}`}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">{column.label}</h3>
          <div className="flex items-center gap-2">
            {column.id === 'backlog' && (
              <button
                onClick={onAddClick}
                className="p-1 rounded hover:bg-white/50 transition-colors"
                title="Add new agent"
              >
                <Plus className="w-4 h-4 text-gray-700" />
              </button>
            )}
            <span className="text-xs font-medium text-gray-600 bg-white px-2 py-0.5 rounded-full">
              {agents.length}
            </span>
          </div>
        </div>
      </div>

      {/* Cards - Full height droppable area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[200px]">
        <SortableContext
          items={agents.map(a => a.instance_id)}
          strategy={verticalListSortingStrategy}
        >
          {agents.length === 0 ? (
            <div className="text-center text-gray-400 text-sm py-8">
              Drop sessions here
            </div>
          ) : (
            agents.map((agent) => (
              <DraggableCard
                key={agent.instance_id}
                agent={agent}
                characters={characters}
                onClick={() => onCardClick(agent)}
                onDelete={onDeleteCard}
              />
            ))
          )}
        </SortableContext>
      </div>
    </div>
  );
}

// Create/Edit Project Dialog
function CreateProjectDialog({
  project,
  onClose,
  onCreate,
}: {
  project?: Project;
  onClose: () => void;
  onCreate: (project: Project) => void;
}) {
  const isEditMode = !!project;
  const [name, setName] = useState(project?.name || '');
  const [description, setDescription] = useState(project?.description || '');
  const [pmId, setPmId] = useState<string>(project?.pm_id || '');
  const [teamMemberIds, setTeamMemberIds] = useState<string[]>(project?.team_member_ids || []);
  const [creating, setCreating] = useState(false);
  const [characters, setCharacters] = useState<CharacterMetadata[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Load characters on mount
  useEffect(() => {
    api.getCharactersLibrary().then(setCharacters).catch(console.error);
  }, []);

  const toggleTeamMember = (charId: string) => {
    setTeamMemberIds(prev =>
      prev.includes(charId)
        ? prev.filter(id => id !== charId)
        : [...prev, charId]
    );
  };

  const handleCreate = async () => {
    if (!name.trim()) return;

    setCreating(true);
    try {
      let resultProject;
      if (isEditMode && project) {
        // Update existing project
        resultProject = await api.updateProject(project.id, {
          name: name.trim(),
          description: description.trim() || undefined,
          pm_id: pmId || undefined,
          team_member_ids: teamMemberIds.length > 0 ? teamMemberIds : undefined,
        });
      } else {
        // Create new project
        resultProject = await api.createProject({
          name: name.trim(),
          description: description.trim() || undefined,
          pm_id: pmId || undefined,
          team_member_ids: teamMemberIds.length > 0 ? teamMemberIds : undefined,
        });
      }
      onCreate(resultProject);
      onClose();
    } catch (error) {
      alert(`Failed to ${isEditMode ? 'update' : 'create'} project: ` + error);
    } finally {
      setCreating(false);
    }
  };

  // Filter characters by search query
  const filteredCharacters = characters.filter(char => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      char.name.toLowerCase().includes(query) ||
      (char.description && char.description.toLowerCase().includes(query))
    );
  });

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl border border-gray-200 shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="px-6 py-4">
          <h2 className="text-2xl font-bold text-gray-900">
            {isEditMode ? 'Edit Project' : 'Create New Project'}
          </h2>
        </div>

        {/* Two-column layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Team Member Selector */}
          <div className="w-1/2 border-r border-gray-200 flex flex-col">
            {/* Character List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {characters.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <p className="text-sm">Loading team members...</p>
                </div>
              ) : filteredCharacters.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <p className="text-sm">No team members found</p>
                  <p className="text-xs text-gray-400 mt-1">Try a different search term</p>
                </div>
              ) : (
                filteredCharacters.map((char) => {
                  const isSelected = teamMemberIds.includes(char.id);
                  const isPM = pmId === char.id;
                  return (
                    <button
                      key={char.id}
                      onClick={() => toggleTeamMember(char.id)}
                      className={cn(
                        'w-full p-4 rounded-xl border-2 text-left transition-all hover:shadow-md relative',
                        isSelected
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                      )}
                    >
                      {/* Header with Avatar and Name */}
                      <div className="flex items-start gap-3">
                        <Avatar seed={char.avatar || char.name} size={48} className="w-12 h-12 flex-shrink-0" color={char.color} />
                        <div className="flex-1 min-w-0">
                          {/* Name and PM badge */}
                          <div className="flex items-center gap-2 mb-1">
                            <div className="font-bold text-gray-900 text-base">{char.name}</div>
                            {isPM && (
                              <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-800 rounded font-medium">
                                PM
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-gray-600 line-clamp-2">
                            {char.description || 'No description'}
                          </div>
                        </div>

                        {/* Right side badges - aligned */}
                        <div className="flex items-start gap-2 flex-shrink-0">
                          {/* Selection Checkmark */}
                          {isSelected && (
                            <div className="w-6 h-6 rounded-full bg-primary-500 flex items-center justify-center">
                              <span className="text-white text-sm">✓</span>
                            </div>
                          )}

                          {/* PM Star Badge */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setPmId(isPM ? '' : char.id);
                            }}
                            className={cn(
                              'w-6 h-6 rounded-full flex items-center justify-center transition-all',
                              isPM
                                ? 'bg-yellow-400 text-white scale-110'
                                : 'bg-gray-200 text-gray-400 hover:bg-yellow-200 hover:text-yellow-600'
                            )}
                            title={isPM ? 'Remove as PM' : 'Set as PM'}
                          >
                            <span className="text-sm">★</span>
                          </button>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            {/* Search Bar */}
            <div className="p-4 border-t border-gray-200">
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search team members..."
              />
            </div>
          </div>

          {/* Right: Project Configuration */}
          <div className="w-1/2 flex flex-col">
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Project Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Project Name <span className="text-red-500">*</span>
                </label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., My Awesome Project"
                  className="w-full"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of your project..."
                  rows={4}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                />
              </div>

              {/* Selected Team Preview */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Selected Team ({teamMemberIds.length}{pmId ? ', 1 PM' : ''})
                </label>
                {teamMemberIds.length === 0 ? (
                  <div className="p-4 rounded-lg border-2 border-dashed border-gray-300 text-center">
                    <p className="text-sm text-gray-500">No team members selected</p>
                    <p className="text-xs text-gray-400 mt-1">Select members from the left panel</p>
                  </div>
                ) : (
                  <div className="h-[28vh] overflow-y-auto space-y-2 scrollbar-hide p-3 bg-gray-50 rounded-lg border border-gray-200">
                    {teamMemberIds.map((charId) => {
                      const char = characters.find(c => c.id === charId);
                      if (!char) return null;
                      const isPM = pmId === charId;
                      return (
                        <div
                          key={charId}
                          className="relative p-3 rounded-lg border border-gray-200 bg-white hover:border-gray-300 transition-all"
                        >
                          <button
                            onClick={() => toggleTeamMember(charId)}
                            className="absolute top-2 right-2 w-5 h-5 bg-white hover:bg-red-500 rounded-full flex items-center justify-center border border-gray-300 hover:border-red-500 transition-all shadow-sm group z-10"
                            title="Remove from team"
                          >
                            <Plus className="w-3 h-3 text-gray-600 group-hover:text-white rotate-45 transition-colors" />
                          </button>
                          <div className="flex items-start gap-3">
                            <Avatar seed={char.avatar || char.name} size={40} className="w-10 h-10 flex-shrink-0" color={char.color} />
                            <div className="flex-1 min-w-0 pr-6">
                              <div className="flex items-center gap-2">
                                <div className="font-medium text-gray-900 text-sm truncate">
                                  {char.name}
                                </div>
                                {isPM && (
                                  <span className="flex-shrink-0 text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-800 rounded font-medium">
                                    ★ PM
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-gray-500 line-clamp-2 mt-0.5">
                                {char.description || 'No description'}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="p-6">
              <Button
                variant="primary"
                onClick={handleCreate}
                className="w-full"
                disabled={!name.trim() || creating}
                loading={creating}
              >
                {creating ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Project' : 'Create Project')}
              </Button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// Spawn Dialog - full implementation from original Workplace
function SpawnDialog({
  characters,
  selectedProject,
  initialStage = 'backlog',
  onClose,
  onSpawn,
}: {
  characters: CharacterMetadata[];
  selectedProject: Project | null;
  initialStage?: string;
  onClose: () => void;
  onSpawn: (agent: AgentInstance) => void;
}) {
  const [selectedTeam, setSelectedTeam] = useState<string[]>([]);
  const [sessionDescription, setSessionDescription] = useState('');
  const [kanbanStage, setKanbanStage] = useState(initialStage);
  const [spawning, setSpawning] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [skills, setSkills] = useState<any[]>([]);

  // Load skills on mount
  useEffect(() => {
    api.getSkills().then(setSkills).catch(console.error);
  }, []);

  const toggleCharacter = (charId: string) => {
    setSelectedTeam(prev => {
      const newSelection = prev.includes(charId)
        ? prev.filter(id => id !== charId)
        : [...prev, charId];
      console.log('[FRONTEND] Toggle character', charId, '-> selectedTeam:', newSelection);
      return newSelection;
    });
  };

  const removeFromTeam = (charId: string) => {
    setSelectedTeam(prev => prev.filter(id => id !== charId));
  };

  const filteredCharacters = characters.filter(char => {
    // Only show characters that are in the selected project's team
    if (selectedProject && selectedProject.team_member_ids) {
      if (!selectedProject.team_member_ids.includes(char.id)) {
        return false;
      }
    }

    // Then filter by search query
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      char.name.toLowerCase().includes(query) ||
      char.description.toLowerCase().includes(query)
    );
  });

  const handleSpawn = async () => {
    if (selectedTeam.length === 0 || !sessionDescription) return;

    console.log('[FRONTEND] Spawning with selectedTeam:', selectedTeam);
    setSpawning(true);
    try {
      // Determine role based on team size
      // If only 1 agent selected, use that agent directly (single_specialist)
      // If multiple agents selected, use orchestrator to coordinate them
      const role = selectedTeam.length === 1 ? 'single_specialist' : 'orchestrator';

      // Build system prompt based on role
      let systemPromptAppend = '';
      if (role === 'orchestrator') {
        // For orchestrator: Add goal context for specialists
        systemPromptAppend = `Goal: ${sessionDescription}

Share this goal with your team members when calling them. Make sure they understand the overall objective before working on their specific tasks.`;
      } else {
        // For single_specialist: Add goal as task context
        systemPromptAppend = `Task: ${sessionDescription}`;
      }

      const payload = {
        team_member_ids: selectedTeam,  // For orchestrator: specialists; For single_specialist: the single character
        project_id: selectedProject?.id,  // Include project_id from selected project
        project_path: selectedProject?.path || paths.projectRoot,  // Use project path from selected project
        session_description: sessionDescription,  // Still shown in UI as description
        system_prompt_append: systemPromptAppend,  // Goal/task goes in system prompt
        kanban_stage: kanbanStage,  // Include selected kanban stage
        role: role,  // Specify role explicitly
      };
      console.log('[FRONTEND] Sending payload with role:', role, payload);
      const agent = await api.launchSession(payload);
      onSpawn(agent);
    } catch (error) {
      alert('Failed to launch session: ' + error);
    } finally {
      setSpawning(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl border border-gray-200 shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="px-6 py-4">
          <h2 className="text-2xl font-bold text-gray-900">Start a new session</h2>
        </div>

        {/* Two-column layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Agent Selector */}
          <div className="w-1/2 border-r border-gray-200 flex flex-col">
            {/* Character List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {filteredCharacters.map((char) => {
                const isSelected = selectedTeam.includes(char.id);
                return (
                  <button
                    key={char.id}
                    onClick={() => toggleCharacter(char.id)}
                    className={cn(
                      'w-full p-4 rounded-xl border-2 text-left transition-all hover:shadow-md',
                      isSelected
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 bg-white hover:border-gray-300'
                    )}
                  >
                    {/* Header with Avatar and Name */}
                    <div className="flex items-start gap-3">
                      <Avatar seed={char.avatar || char.name} size={48} className="w-12 h-12 flex-shrink-0" color={char.color} />
                      <div className="flex-1 min-w-0">
                        {/* Name and Skills */}
                        <div className="flex items-center gap-2 mb-1">
                          <div className="font-bold text-gray-900 text-base">{char.name}</div>
                          {/* Skills */}
                          {char.skills && char.skills.length > 0 && (
                            <div className="flex items-center -space-x-1">
                              {char.skills.slice(0, 5).map((skillId) => {
                                const skill = skills.find(s => s.id === skillId);
                                if (!skill) return null;
                                const IconComponent = getSkillIcon(skill.icon);
                                return (
                                  <div
                                    key={skillId}
                                    className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${skill.iconColor ? '' : 'bg-gray-100'}`}
                                    style={skill.iconColor ? { backgroundColor: skill.iconColor } : undefined}
                                    title={skill.name}
                                  >
                                    <IconComponent className="w-3 h-3 text-white" />
                                  </div>
                                );
                              })}
                              {char.skills.length > 5 && (
                                <div className={cn(
                                  "w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium",
                                  isSelected
                                    ? "bg-primary-200 text-primary-700"
                                    : "bg-gray-200 text-gray-600"
                                )}>
                                  +{char.skills.length - 5}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        <div className="text-sm text-gray-600 line-clamp-2">
                          {char.description}
                        </div>
                      </div>
                      {isSelected && (
                        <div className="w-6 h-6 rounded-full bg-primary-500 flex items-center justify-center flex-shrink-0">
                          <span className="text-white text-sm">✓</span>
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Search Bar */}
            <div className="p-4 border-t border-gray-200">
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search agents..."
              />
            </div>
          </div>

          {/* Right: Configuration */}
          <div className="w-1/2 flex flex-col">
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Session Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Session Description <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={sessionDescription}
                  onChange={(e) => setSessionDescription(e.target.value)}
                  placeholder="What should this agent do?"
                  rows={6}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                />
              </div>

              {/* Team */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Team ({selectedTeam.length})
                  {selectedTeam.length === 1 && (
                    <span className="ml-2 text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                      Direct mode
                    </span>
                  )}
                  {selectedTeam.length > 1 && (
                    <span className="ml-2 text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full">
                      Orchestrator mode
                    </span>
                  )}
                </label>
                {selectedTeam.length === 0 ? (
                  <div className="p-4 rounded-lg border-2 border-dashed border-gray-300 text-center">
                    <p className="text-sm text-gray-500">No agents selected</p>
                    <p className="text-xs text-gray-400 mt-1">Select agents from the left panel</p>
                  </div>
                ) : (
                  <div className="h-[28vh] overflow-y-auto space-y-2 scrollbar-hide p-3 bg-gray-50 rounded-lg border border-gray-200">
                    {selectedTeam.map((charId) => {
                      const char = characters.find(c => c.id === charId);
                      if (!char) return null;
                      return (
                        <div
                          key={charId}
                          className="relative p-3 rounded-lg border border-gray-200 bg-white hover:border-gray-300 transition-all"
                        >
                          <button
                            onClick={() => removeFromTeam(charId)}
                            className="absolute top-2 right-2 w-5 h-5 bg-white hover:bg-red-500 rounded-full flex items-center justify-center border border-gray-300 hover:border-red-500 transition-all shadow-sm group z-10"
                          >
                            <Plus className="w-3 h-3 text-gray-600 group-hover:text-white rotate-45 transition-colors" />
                          </button>
                          <div className="flex items-start gap-3">
                            <Avatar seed={char.avatar || char.name} size={40} className="w-10 h-10 flex-shrink-0" color={char.color} />
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-gray-900 text-sm truncate">
                                {char.name}
                              </div>
                              <div className="text-xs text-gray-500 line-clamp-2 mt-0.5">
                                {char.description}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="p-6">
              <Button
                variant="primary"
                onClick={handleSpawn}
                disabled={selectedTeam.length === 0 || !sessionDescription || spawning}
                loading={spawning}
                className="w-full"
              >
                {spawning ? 'Creating...' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
