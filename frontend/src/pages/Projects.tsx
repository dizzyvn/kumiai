/**
 * Projects - Project management page with PM chat integration
 *
 * Two-column layout:
 * - Left: Projects sidebar with compact cards
 * - Right: PM chat session for selected project
 */
import { useState, useEffect } from 'react';
import { Plus, Edit2, Archive, Folder, ExternalLink, Briefcase, Search, List, Loader2, ArchiveRestore, Trash2 } from 'lucide-react';
import { api, Project, CreateProjectRequest, UpdateProjectRequest, AgentInstance, AgentCharacter } from '@/lib/api';
import { cn } from '@/lib/utils';
import { layout } from '@/styles/design-system';
import { Avatar } from '@/components/Avatar';
import { UnifiedSessionChat } from '@/components/UnifiedSessionChat';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { MobileDrawer } from '@/components/ui/MobileDrawer';
import { MobileHeader } from '@/components/MobileHeader';

interface ProjectsProps {
  currentProjectId?: string;
  onProjectSelect?: (projectId: string | null) => void;
}

export function Projects({ currentProjectId, onProjectSelect }: ProjectsProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // PM Chat state
  const [pmSession, setPmSession] = useState<AgentInstance | null>(null);
  const [pmSessionLoading, setPmSessionLoading] = useState(false);
  const [characters, setCharacters] = useState<AgentCharacter[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Track all PM sessions and their message counts
  const [allPmSessions, setAllPmSessions] = useState<Map<string, AgentInstance>>(new Map());
  const [pmMessageCounts, setPmMessageCounts] = useState<Map<string, number>>(new Map());
  const [allSessions, setAllSessions] = useState<AgentInstance[]>([]);
  const [allPmSessionsLoaded, setAllPmSessionsLoaded] = useState(false);
  const [lastViewedMessageCounts, setLastViewedMessageCounts] = useState<Map<string, number>>(() => {
    // Load from localStorage
    const saved = localStorage.getItem('lastViewedPmMessageCounts');
    if (saved) {
      try {
        const data = JSON.parse(saved);
        return new Map(Object.entries(data));
      } catch {
        return new Map();
      }
    }
    return new Map();
  });

  const navigate = useNavigate();

  // Helper function to update selected project (uses URL for both mobile and desktop)
  const selectProject = (projectId: string | null) => {
    if (projectId) {
      navigate(`/projects?project=${projectId}`, { replace: true });
      onProjectSelect?.(projectId);
    } else {
      navigate('/projects', { replace: true });
      onProjectSelect?.(null); // Notify parent that no project is selected
    }
  };

  useEffect(() => {
    loadProjects();
    loadCharacters();
    loadAllPmSessions();

    // Poll for new messages every 60 seconds (reduced from 30)
    const interval = setInterval(() => {
      loadAllPmSessions();
    }, 60000);

    return () => clearInterval(interval);
  }, [showArchived]);

  // Load PM session when project is selected
  useEffect(() => {
    if (currentProjectId) {
      loadPmSession(currentProjectId);
      // Mark messages as viewed when selecting a project
      const session = allPmSessions.get(currentProjectId);
      if (session) {
        const currentCount = pmMessageCounts.get(currentProjectId) || 0;
        setLastViewedMessageCounts(prev => {
          const newMap = new Map(prev);
          newMap.set(currentProjectId, currentCount);
          // Save to localStorage
          localStorage.setItem('lastViewedPmMessageCounts', JSON.stringify(Object.fromEntries(newMap)));
          return newMap;
        });
      }
    } else {
      setPmSession(null);
    }
  }, [currentProjectId, allPmSessions, pmMessageCounts]);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const data = await api.getProjects(showArchived);
      setProjects(data);

      // Auto-select first project if none selected (desktop only)
      // On mobile, we show the project list when nothing is selected
      const isDesktop = window.matchMedia('(min-width: 1024px)').matches;
      if (isDesktop && !currentProjectId && data.length > 0 && !data[0].is_archived) {
        selectProject(data[0].id);
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadCharacters = async () => {
    try {
      const chars = await api.getCharacters();
      setCharacters(chars);
    } catch (error) {
      console.error('Failed to load characters:', error);
    }
  };

  const loadAllPmSessions = async () => {
    try {
      const sessions = await api.getSessions();
      const pmSessions = sessions.filter(s => s.role === 'pm');

      // Store all sessions for running count
      setAllSessions(sessions);

      // Get all projects (including archived) to check which PM sessions to load
      const allProjects = await api.getProjects(true); // true = include archived
      const archivedProjectIds = new Set(
        allProjects.filter(p => p.is_archived).map(p => p.id)
      );

      // Filter out PM sessions that belong to archived projects
      const activePmSessions = pmSessions.filter(
        session => !archivedProjectIds.has(session.project_id)
      );

      // Create a map of project_id -> session
      const sessionMap = new Map<string, AgentInstance>();
      const messageCountMap = new Map<string, number>();

      // Load message counts for each active PM session only
      await Promise.all(activePmSessions.map(async (session) => {
        sessionMap.set(session.project_id, session);

        try {
          const messages = await api.getSessionMessages(session.instance_id, 1000);
          messageCountMap.set(session.project_id, messages.length);
        } catch (error) {
          console.error(`Failed to load messages for session ${session.instance_id}:`, error);
          messageCountMap.set(session.project_id, 0);
        }
      }));

      setAllPmSessions(sessionMap);
      setPmMessageCounts(messageCountMap);
      setAllPmSessionsLoaded(true);
    } catch (error) {
      console.error('Failed to load PM sessions:', error);
      setAllPmSessionsLoaded(true); // Still mark as loaded even on error
    }
  };

  const loadPmSession = async (projectId: string) => {
    setPmSessionLoading(true);
    try {
      const session = allPmSessions.get(projectId);
      setPmSession(session || null);
    } catch (error) {
      console.error('Failed to load PM session:', error);
      setPmSession(null);
    } finally {
      setPmSessionLoading(false);
    }
  };

  const handleRecreatePmSession = async (projectId: string) => {
    if (!confirm('This will recreate the PM session. All existing conversation history will be lost. Continue?')) {
      return;
    }

    setPmSessionLoading(true);
    try {
      await api.recreatePmSession(projectId);

      // Poll for PM session initialization (created in background)
      // Max 60 seconds, check every 2 seconds
      let attempts = 0;
      const maxAttempts = 30;
      const pollInterval = 2000;

      const pollForPmSession = async () => {
        attempts++;
        console.log(`Polling for new PM session initialization (attempt ${attempts}/${maxAttempts})...`);

        try {
          const sessions = await api.getSessions();
          const pmSession = sessions.find(s => s.project_id === projectId && s.role === 'pm');

          if (pmSession) {
            console.log(`PM session status: ${pmSession.status}`);

            // Check if initialization completed (status changed from 'initializing')
            if (pmSession.status !== 'initializing') {
              console.log(`PM session recreated and initialized after ${attempts} attempts`);
              // Reload all PM sessions to update the UI
              await loadAllPmSessions();
              // Reload the PM session for this project (will force UnifiedSessionChat to remount)
              await loadPmSession(projectId);
              alert('PM session recreated successfully!');
              setPmSessionLoading(false);
              return;
            }
          } else {
            console.warn(`PM session not found for project ${projectId}`);
          }
        } catch (error) {
          console.error('Error polling for PM session:', error);
        }

        if (attempts < maxAttempts) {
          setTimeout(pollForPmSession, pollInterval);
        } else {
          console.warn(`PM session still initializing after ${maxAttempts} attempts, giving up polling`);
          // Still reload PM sessions to show whatever state exists
          await loadAllPmSessions();
          await loadPmSession(projectId);
          alert('PM session recreation started, but initialization is taking longer than expected. Please refresh if needed.');
          setPmSessionLoading(false);
        }
      };

      // Load PM sessions immediately to show initializing state
      await loadAllPmSessions();
      await loadPmSession(projectId);

      // Start polling after a short delay
      setTimeout(pollForPmSession, 2000);
    } catch (error) {
      console.error('Failed to recreate PM session:', error);
      alert(error instanceof Error ? error.message : 'Failed to recreate PM session');
      setPmSessionLoading(false);
    }
  };

  const handleCreateProject = async (data: CreateProjectRequest) => {
    try {
      const newProject = await api.createProject(data);
      await loadProjects();
      setIsCreating(false);

      // Poll for PM session initialization (created in background)
      if (newProject.id) {
        // Auto-select the newly created project
        selectProject(newProject.id);

        // Poll for PM session initialization (max 60 seconds, check every 2 seconds)
        let attempts = 0;
        const maxAttempts = 30;
        const pollInterval = 2000;

        const pollForPmSession = async () => {
          attempts++;
          console.log(`Polling for PM session initialization (attempt ${attempts}/${maxAttempts})...`);

          // Fetch sessions directly to check PM session status
          try {
            const sessions = await api.getSessions();
            const pmSession = sessions.find(s => s.project_id === newProject.id && s.role === 'pm');

            if (pmSession) {
              console.log(`PM session status: ${pmSession.status}`);

              // Check if initialization completed (status changed from 'initializing')
              if (pmSession.status !== 'initializing') {
                console.log(`PM session initialized for project ${newProject.id} after ${attempts} attempts`);
                // Reload all PM sessions to update the UI
                await loadAllPmSessions();
                return;
              }
            } else {
              console.warn(`PM session not found for project ${newProject.id}`);
            }
          } catch (error) {
            console.error('Error polling for PM session:', error);
          }

          if (attempts < maxAttempts) {
            setTimeout(pollForPmSession, pollInterval);
          } else {
            console.warn(`PM session still initializing after ${maxAttempts} attempts, giving up polling`);
            // Still reload PM sessions to show whatever state exists
            await loadAllPmSessions();
          }
        };

        // Load PM sessions immediately to show initializing state
        await loadAllPmSessions();

        // Start polling after a short delay
        setTimeout(pollForPmSession, 2000);
      }
    } catch (error) {
      console.error('Failed to create project:', error);
      alert(error instanceof Error ? error.message : 'Failed to create project');
    }
  };

  const handleUpdateProject = async (projectId: string, data: UpdateProjectRequest) => {
    try {
      await api.updateProject(projectId, data);
      await loadProjects();
      setEditingProject(null);
    } catch (error) {
      console.error('Failed to update project:', error);
      alert(error instanceof Error ? error.message : 'Failed to update project');
    }
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm('Are you sure you want to archive this project?')) {
      return;
    }

    try {
      await api.deleteProject(projectId);
      await loadProjects();

      // Clear selection if current project was deleted
      if (currentProjectId === projectId) {
        onProjectSelect?.('');
        navigate('/projects', { replace: true });
      }
    } catch (error) {
      console.error('Failed to delete project:', error);
      alert(error instanceof Error ? error.message : 'Failed to archive project');
    }
  };

  const handleUnarchiveProject = async (projectId: string) => {
    try {
      await api.unarchiveProject(projectId);
      await loadProjects();
    } catch (error) {
      console.error('Failed to unarchive project:', error);
      alert(error instanceof Error ? error.message : 'Failed to unarchive project');
    }
  };

  const handlePermanentlyDeleteProject = async (projectId: string) => {
    const userConfirmation = prompt(
      '⚠️ WARNING: This will permanently remove the project from the app.\n\n' +
      'Project files on disk will NOT be deleted.\n' +
      'This action CANNOT be undone!\n\n' +
      'Type "DELETE" to confirm:'
    );

    if (userConfirmation !== 'DELETE') {
      return;
    }

    try {
      await api.permanentlyDeleteProject(projectId);
      await loadProjects();

      // Clear selection if current project was deleted
      if (currentProjectId === projectId) {
        onProjectSelect?.('');
        navigate('/projects', { replace: true });
      }
    } catch (error) {
      console.error('Failed to permanently delete project:', error);
      alert(error instanceof Error ? error.message : 'Failed to permanently delete project');
    }
  };

  const handleOpenProject = (projectId: string) => {
    navigate(`/?project=${projectId}`);
  };

  // Filter projects by search query
  const filteredProjects = projects.filter(project => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      project.name.toLowerCase().includes(query) ||
      (project.description && project.description.toLowerCase().includes(query))
    );
  });

  // Projects Sidebar Content (shared between desktop and mobile)
  const projectsSidebarContent = (
    <>
      {/* Search Bar */}
      <div className="h-12 px-2 lg:px-3 bg-white flex items-center flex-shrink-0">
        <div className="flex items-center gap-2 w-full">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search projects..."
              className="w-full pl-10 pr-4 py-1.5 border border-gray-300 bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
            />
          </div>
          <button
            onClick={() => setIsCreating(true)}
            className="flex-shrink-0 p-1.5 bg-primary-500 text-white hover:bg-primary-600 transition-colors"
            title="New Project"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Projects List */}
      <div className="flex-1 overflow-y-auto p-2 pb-24">
        {loading && (
          <div className="p-6 text-center">
            <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
            <p className="text-gray-500">Loading projects...</p>
          </div>
        )}

        {!loading && filteredProjects.length === 0 && (
          <div className="p-6 text-center text-gray-500">
            <Folder className="w-12 h-12 mx-auto mb-2.5 text-gray-400" />
            <p className="text-sm">{searchQuery ? 'No projects found' : showArchived ? 'No archived projects' : 'No projects yet'}</p>
            <p className="text-xs text-gray-400 mt-1">
              {searchQuery ? 'Try a different search term' : 'Create one to get started'}
            </p>
          </div>
        )}

        {!loading && filteredProjects.length > 0 && (
          <div className="flex flex-col">
            {filteredProjects.map((project) => {
              const currentCount = pmMessageCounts.get(project.id) || 0;
              const lastViewedCount = lastViewedMessageCounts.get(project.id) || 0;
              const newMessageCount = Math.max(0, currentCount - lastViewedCount);

              const runningCount = allSessions.filter(
                s => s.project_id === project.id && s.status === 'working'
              ).length;

              return (
                <CompactProjectCard
                  key={project.id}
                  project={project}
                  isSelected={currentProjectId === project.id}
                  characters={characters}
                  newMessageCount={newMessageCount}
                  runningSessionsCount={runningCount}
                  onSelect={() => {
                    selectProject(project.id);
                    setIsDrawerOpen(false); // Close drawer on mobile after selection
                  }}
                  onEdit={() => setEditingProject(project)}
                  onDelete={() => handleDeleteProject(project.id)}
                  onUnarchive={() => handleUnarchiveProject(project.id)}
                  onPermanentDelete={() => handlePermanentlyDeleteProject(project.id)}
                  onOpen={() => handleOpenProject(project.id)}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom Action Container */}
      <div className="flex-shrink-0 bg-white p-4">
        {/* Show archived checkbox - Desktop only */}
        <label className="hidden lg:flex items-center gap-2 text-xs text-gray-600 px-3 py-2 rounded-md border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
            className="rounded"
          />
          Show archived
        </label>
      </div>
    </>
  );

  return (
    <div className="flex-1 flex overflow-hidden bg-white">
      {/* Mobile: Project List (when no project selected) */}
      {!currentProjectId && (
        <div className="flex-1 lg:hidden flex flex-col overflow-hidden">
          {projectsSidebarContent}
        </div>
      )}

      {/* Desktop Sidebar: Projects List */}
      <div className="hidden lg:flex border-r-2 border-primary-500 flex-col relative" style={{ width: layout.sidebarWidth }}>
        {projectsSidebarContent}
      </div>

      {/* Main Content: PM Chat */}
      <div className={cn(
        "flex-1 flex flex-col min-w-0 overflow-hidden",
        currentProjectId ? "pt-0" : "hidden lg:flex lg:pt-0"
      )}>
        {currentProjectId && pmSession && pmSession.status !== 'initializing' ? (
          <UnifiedSessionChat
            key={pmSession.instance_id}
            instanceId={pmSession.instance_id}
            role="pm"
            showHeader={true}
            onClose={() => selectProject(null)}
            onRecreatePm={handleRecreatePmSession}
            onSessionJump={(sessionId) => {
              // When jumping to a session from Projects page, navigate to the Workspace
              // with the session opened
              const project = projects.find(p => p.id === currentProjectId);
              if (project) {
                navigate(`/?project=${project.id}&session=${sessionId}`);
              }
            }}
          />
        ) : currentProjectId && pmSession && pmSession.status === 'initializing' ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-primary-500 animate-spin" />
              <p className="text-gray-700 font-medium">Initializing PM session...</p>
              <p className="text-sm text-gray-500 mt-2">Connecting to Claude and setting up workspace</p>
              <p className="text-xs text-gray-400 mt-1">This usually takes 2-5 seconds</p>
            </div>
          </div>
        ) : currentProjectId && (pmSessionLoading || !allPmSessionsLoaded) ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
              <p className="text-gray-500">Loading PM session...</p>
            </div>
          </div>
        ) : currentProjectId && !pmSession ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Briefcase className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">PM session not found for this project</p>
              <p className="text-sm text-muted-foreground mt-2">The PM session may not have been created yet or has encountered an error</p>
              <Button
                onClick={() => handleRecreatePmSession(currentProjectId)}
                disabled={pmSessionLoading}
                className="mt-4"
              >
                {pmSessionLoading ? 'Recreating...' : 'Recreate PM Session'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Briefcase className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">Select a project</h3>
              <p className="text-muted-foreground">Choose a project from the sidebar to chat with its PM</p>
            </div>
          </div>
        )}
      </div>

      {/* Create/Edit Modal */}
      {(isCreating || editingProject) && (
        <ProjectFormModal
          project={editingProject}
          onSave={(data) => {
            if (editingProject) {
              handleUpdateProject(editingProject.id, data);
            } else {
              handleCreateProject(data as CreateProjectRequest);
            }
          }}
          onClose={() => {
            setIsCreating(false);
            setEditingProject(null);
          }}
        />
      )}
    </div>
  );
}

// Compact Project Card for Sidebar
interface CompactProjectCardProps {
  project: Project;
  isSelected: boolean;
  characters: AgentCharacter[];
  newMessageCount: number;
  runningSessionsCount: number;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onUnarchive: () => void;
  onPermanentDelete: () => void;
  onOpen: () => void;
}

function CompactProjectCard({
  project,
  isSelected,
  characters,
  newMessageCount,
  runningSessionsCount,
  onSelect,
  onEdit,
  onDelete,
  onUnarchive,
  onPermanentDelete,
  onOpen,
}: CompactProjectCardProps) {
  const teamMembers = characters.filter(c =>
    project.team_member_ids?.includes(c.id)
  );

  return (
    <div
      className={cn(
        "border-t-2 border-b-2 cursor-pointer hover:bg-primary-100 transition-all flex flex-col gap-2",
        "px-3 py-2 min-h-[100px] lg:min-h-[100px]", // Desktop: full height, Mobile: auto
        isSelected
          ? "border-primary-500 bg-primary-100"
          : "border-gray-200 bg-white",
        project.is_archived && "opacity-60"
      )}
      onClick={onSelect}
    >
      {/* Project Name and Actions */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-gray-900 truncate flex-1 min-w-0">
          {project.name}
        </h3>
        <div className="flex items-center gap-1 ml-2">
          {runningSessionsCount > 0 && (
            <div className="flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs font-medium">
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
              {runningSessionsCount}
            </div>
          )}
          {newMessageCount > 0 && (
            <div className="flex-shrink-0 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {newMessageCount > 9 ? '9+' : newMessageCount}
            </div>
          )}
          {!project.is_archived && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpen();
              }}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
              title="Open Workspace"
            >
              <List className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
          {!project.is_archived && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
              title="Edit project"
            >
              <Edit2 className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
          {!project.is_archived ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
              title="Archive project"
            >
              <Archive className="w-3.5 h-3.5 text-gray-500" />
            </button>
          ) : (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onUnarchive();
                }}
                className="p-1 hover:bg-green-100 rounded transition-colors"
                title="Unarchive project"
              >
                <ArchiveRestore className="w-3.5 h-3.5 text-green-600" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPermanentDelete();
                }}
                className="p-1 hover:bg-red-100 rounded transition-colors"
                title="Permanently delete project"
              >
                <Trash2 className="w-3.5 h-3.5 text-red-600" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Description and Details */}
      <div className="flex gap-3">
        <div className="flex-1 min-w-0 flex flex-col gap-1">
          {/* Description */}
          {project.description && (
            <p className="text-sm text-gray-600 line-clamp-2">
              {project.description}
            </p>
          )}

          {/* Path - Desktop only */}
          <div className="hidden lg:flex items-center gap-1 text-xs text-gray-500">
            <Folder className="w-3 h-3" />
            <span className="truncate">{project.path?.split('/').pop() || 'project'}</span>
          </div>

          {/* Team Members - Desktop only */}
          {teamMembers.length > 0 && (
            <div className="hidden lg:flex items-center gap-1">
              <MemberAvatars members={teamMembers} />
            </div>
          )}

          {/* Archived badge */}
          {project.is_archived && (
            <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full font-medium self-start">
              Archived
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// Team Member Avatars Component
interface MemberAvatarsProps {
  members: AgentCharacter[];
  maxVisible?: number;
}

function MemberAvatars({ members, maxVisible = 4 }: MemberAvatarsProps) {
  const visibleMembers = members.slice(0, maxVisible);
  const remaining = members.length - maxVisible;

  return (
    <div className="flex items-center -space-x-2">
      {visibleMembers.map((member) => (
        <div
          key={member.id}
          className="relative"
          title={member.name}
        >
          <Avatar
            seed={member.avatar || member.name}
            size={24}
            className="w-6 h-6 border-2 border-background"
            color={member.color}
          />
        </div>
      ))}
      {remaining > 0 && (
        <div
          className="w-6 h-6 rounded-full bg-muted border-2 border-background flex items-center justify-center"
          title={`${remaining} more member${remaining > 1 ? 's' : ''}`}
        >
          <span className="text-[10px] font-medium text-muted-foreground">+{remaining}</span>
        </div>
      )}
    </div>
  );
}

// Project Form Modal (keeping existing implementation)
interface ProjectFormModalProps {
  project: Project | null;
  onSave: (data: CreateProjectRequest | UpdateProjectRequest) => void;
  onClose: () => void;
}

function ProjectFormModal({ project, onSave, onClose }: ProjectFormModalProps) {
  const [formData, setFormData] = useState({
    name: project?.name || '',
    description: project?.description || '',
    pm_id: project?.pm_id || '',
    team_member_ids: project?.team_member_ids || [],
    path: project?.path || '',
  });
  const [characters, setCharacters] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [mobileTab, setMobileTab] = useState<'details' | 'team'>('details');

  useEffect(() => {
    import('../lib/api').then(({ api }) => {
      api.getCharactersLibrary().then(setCharacters).catch(console.error);
    });
  }, []);

  const toggleTeamMember = (charId: string) => {
    setFormData(prev => {
      const isCurrentlySelected = prev.team_member_ids.includes(charId);
      const newTeamMemberIds = isCurrentlySelected
        ? prev.team_member_ids.filter(id => id !== charId)
        : [...prev.team_member_ids, charId];

      // Auto-set PM when only one agent is selected
      let newPmId = prev.pm_id;
      if (newTeamMemberIds.length === 1) {
        newPmId = newTeamMemberIds[0];
      } else if (isCurrentlySelected && prev.pm_id === charId) {
        // Clear PM if removing the current PM
        newPmId = '';
      }

      return {
        ...prev,
        team_member_ids: newTeamMemberIds,
        pm_id: newPmId,
      };
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      alert('Project name is required');
      return;
    }

    onSave({
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      path: formData.path.trim() || undefined,
      pm_id: formData.pm_id || undefined,
      team_member_ids: formData.team_member_ids.length > 0 ? formData.team_member_ids : undefined,
    });
  };

  const filteredCharacters = characters.filter(char => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      char.name.toLowerCase().includes(query) ||
      (char.description && char.description.toLowerCase().includes(query))
    );
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-0 lg:p-4">
      <div className="bg-white rounded-none lg:rounded-lg shadow-xl max-w-5xl w-full h-full lg:h-auto lg:max-h-[90vh] flex flex-col">
        <form onSubmit={handleSubmit} className="flex flex-col h-full">
          {/* Header */}
          <div className="px-4 lg:px-6 py-3 lg:py-4 border-b border-gray-200">
            <h2 className="text-base lg:text-lg font-semibold text-gray-900">
              {project ? 'Edit Project' : 'New Project'}
            </h2>
          </div>

          {/* Mobile Tabs */}
          <div className="lg:hidden flex border-b border-gray-200 bg-gray-50">
            <button
              type="button"
              onClick={() => setMobileTab('details')}
              className={cn(
                'flex-1 px-4 py-3 text-sm font-medium transition-colors',
                mobileTab === 'details'
                  ? 'text-primary-600 border-b-2 border-primary-600 bg-white'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              Project Details
            </button>
            <button
              type="button"
              onClick={() => setMobileTab('team')}
              className={cn(
                'flex-1 px-4 py-3 text-sm font-medium transition-colors',
                mobileTab === 'team'
                  ? 'text-primary-600 border-b-2 border-primary-600 bg-white'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              Team ({formData.team_member_ids.length})
            </button>
          </div>

          {/* Body - Two Column Layout (stacked on mobile) */}
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
            {/* Mobile: Project Details Tab */}
            {mobileTab === 'details' && (
              <div className="flex-1 lg:hidden overflow-y-auto p-4 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Project Name *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={3}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Project Path (Optional)
                  </label>
                  <input
                    type="text"
                    value={formData.path}
                    onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                    placeholder="~/my-project or /absolute/path/to/project"
                  />
                  <div className="mt-1.5 space-y-1">
                    <p className="text-xs text-gray-500">
                      💡 Leave empty to auto-generate in ~/projects/{'{project-id}'}
                    </p>
                    <p className="text-xs text-gray-400">
                      Supports ~ for home directory (e.g., ~/Documents/my-project)
                    </p>
                  </div>
                </div>

              </div>
            )}

            {/* Mobile: Team Selection Tab */}
            {mobileTab === 'team' && (
              <div className="flex-1 lg:hidden flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                <h3 className="text-sm font-semibold text-gray-700">Team Members</h3>
                <p className="text-xs text-gray-500 mt-1">
                  {formData.team_member_ids.length} selected • Tap to select/deselect • Star for PM
                </p>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {filteredCharacters.map((char) => {
                  const isSelected = formData.team_member_ids.includes(char.id);
                  const isPM = formData.pm_id === char.id;

                  return (
                    <div
                      key={char.id}
                      onClick={() => toggleTeamMember(char.id)}
                      className={cn(
                        'p-3 rounded-lg border-2 cursor-pointer transition-all',
                        isSelected
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 active:bg-gray-50'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <Avatar seed={char.avatar || char.name} size={40} className="w-10 h-10 flex-shrink-0" color={char.color} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold text-gray-900 text-sm">{char.name}</span>
                            {isPM && (
                              <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-800 rounded font-medium">
                                PM
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-600 line-clamp-2">
                            {char.description || 'No description'}
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isSelected) {
                                setFormData(prev => ({ ...prev, pm_id: isPM ? '' : char.id }));
                              }
                            }}
                            disabled={!isSelected}
                            className={cn(
                              'w-6 h-6 rounded-full flex items-center justify-center transition-all',
                              isPM
                                ? 'bg-yellow-400 text-white'
                                : isSelected
                                ? 'bg-gray-200 text-gray-400 active:bg-yellow-200'
                                : 'bg-gray-100 text-gray-300'
                            )}
                            title={isPM ? 'Remove as PM' : 'Set as PM'}
                          >
                            <span className="text-sm">★</span>
                          </button>
                          <div className={cn(
                            "w-6 h-6 rounded-full flex items-center justify-center transition-all border-2",
                            isSelected
                              ? 'bg-primary-500 border-primary-500'
                              : 'bg-white border-gray-300'
                          )}>
                            {isSelected && <span className="text-white text-xs font-bold">✓</span>}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="p-3 border-t border-gray-200">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search team members..."
                  className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              </div>
            )}

            {/* Desktop: Two Column Layout */}
            <div className="hidden lg:flex lg:w-1/2 border-r border-gray-200 flex-col">
              <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                <h3 className="text-sm font-semibold text-gray-700">Team Members</h3>
                <p className="text-xs text-gray-500 mt-1">Click to select team members, star to set PM</p>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {filteredCharacters.map((char) => {
                  const isSelected = formData.team_member_ids.includes(char.id);
                  const isPM = formData.pm_id === char.id;

                  return (
                    <div
                      key={char.id}
                      onClick={() => toggleTeamMember(char.id)}
                      className={cn(
                        'p-3 rounded-lg border-2 cursor-pointer transition-all',
                        isSelected
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <Avatar seed={char.avatar || char.name} size={40} className="w-10 h-10 flex-shrink-0" color={char.color} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold text-gray-900 text-sm">{char.name}</span>
                            {isPM && (
                              <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-800 rounded font-medium">
                                PM
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-600 line-clamp-2">
                            {char.description || 'No description'}
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          {isSelected && (
                            <div className="w-5 h-5 rounded-full bg-primary-500 flex items-center justify-center">
                              <span className="text-white text-xs">✓</span>
                            </div>
                          )}
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setFormData(prev => ({ ...prev, pm_id: isPM ? '' : char.id }));
                            }}
                            className={cn(
                              'w-5 h-5 rounded-full flex items-center justify-center transition-all',
                              isPM
                                ? 'bg-yellow-400 text-white'
                                : 'bg-gray-200 text-gray-400 hover:bg-yellow-200'
                            )}
                            title={isPM ? 'Remove as PM' : 'Set as PM'}
                          >
                            <span className="text-xs">★</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="p-3 border-t border-gray-200">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search team members..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>

            {/* Desktop: Project Settings */}
            <div className="hidden lg:flex lg:w-1/2 overflow-y-auto p-6 space-y-4 min-h-0 flex-col">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Project Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="My Project"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="What is this project about?"
                  rows={3}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Project Path (Optional)
                </label>
                <input
                  type="text"
                  value={formData.path}
                  onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                  placeholder="~/my-project or /absolute/path/to/project"
                />
                <div className="mt-1.5 space-y-1">
                  <p className="text-xs text-gray-500">
                    💡 Leave empty to auto-generate in ~/projects/{'{project-id}'}
                  </p>
                  <p className="text-xs text-gray-400">
                    Supports ~ for home directory (e.g., ~/Documents/my-project)
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Selected Team ({formData.team_member_ids.length}{formData.pm_id ? ', 1 PM' : ''})
                </label>
                {formData.team_member_ids.length === 0 ? (
                  <div className="p-4 rounded-lg border-2 border-dashed border-gray-300 text-center">
                    <p className="text-sm text-gray-500">No team members selected</p>
                    <p className="text-xs text-gray-400 mt-1">Select members from the left panel</p>
                  </div>
                ) : (
                  <div className="max-h-[28vh] overflow-y-auto space-y-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    {formData.team_member_ids.map((charId) => {
                      const char = characters.find(c => c.id === charId);
                      if (!char) return null;
                      const isPM = formData.pm_id === charId;
                      return (
                        <div
                          key={charId}
                          className="relative p-3 rounded-lg border border-gray-200 bg-white hover:border-gray-300 transition-all"
                        >
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleTeamMember(charId);
                            }}
                            className="absolute top-2 right-2 w-5 h-5 bg-white hover:bg-red-500 rounded-full flex items-center justify-center border border-gray-300 hover:border-red-500 transition-all shadow-sm group z-10"
                            title="Remove from team"
                            type="button"
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
          </div>

          {/* Footer */}
          <div className="px-4 lg:px-6 py-3 lg:py-4 border-t border-gray-200 flex flex-col-reverse lg:flex-row justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="w-full lg:w-auto px-4 py-2.5 lg:py-2 text-gray-700 hover:bg-gray-100 rounded-md transition-colors font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="w-full lg:w-auto px-4 py-2.5 lg:py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 transition-colors font-medium"
            >
              {project ? 'Save Changes' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
