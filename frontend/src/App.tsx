import { useState, useEffect } from 'react';
import { Routes, Route, Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { BookOpen, Users, Briefcase, FolderKanban, User } from 'lucide-react';
import { cn, components } from './styles/design-system';
import WorkplaceKanban from './pages/WorkplaceKanban';
import Skills from './pages/Skills';
import Agents from './pages/Agents';
import { Projects } from './pages/Projects';
import UserProfile from './pages/UserProfile';
import { ProjectSwitcher } from './components/ProjectSwitcher';
import { ErrorBoundary } from './components/ErrorBoundary';
import { BottomNav } from './components/BottomNav';
import { desktopNotifications } from './lib/notifications';
import type { ChatContext } from '@/types/chat';

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Initialize chat context from localStorage (kept for backward compatibility)
  const [chatContext, setChatContext] = useState<ChatContext>(() => {
    try {
      const saved = localStorage.getItem('chatContext');
      return saved ? JSON.parse(saved) : { type: null };
    } catch {
      return { type: null };
    }
  });
  const [showProjectSwitcher, setShowProjectSwitcher] = useState(false);

  // Get project ID from URL params first, then fall back to localStorage
  const projectIdFromUrl = searchParams.get('project');
  const [currentProjectId, setCurrentProjectId] = useState<string | undefined>(() => {
    if (projectIdFromUrl) {
      return projectIdFromUrl;
    }
    const saved = localStorage.getItem('currentProjectId');
    return saved || undefined;
  });
  const [currentProjectName, setCurrentProjectName] = useState<string>('');

  // Sync currentProjectId with URL params changes
  useEffect(() => {
    const urlProjectId = searchParams.get('project');
    if (urlProjectId !== currentProjectId) {
      setCurrentProjectId(urlProjectId || undefined);
    }
  }, [searchParams]);

  // Sync currentProjectId with localStorage
  useEffect(() => {
    if (currentProjectId) {
      localStorage.setItem('currentProjectId', currentProjectId);
    } else {
      localStorage.removeItem('currentProjectId');
    }
  }, [currentProjectId]);

  // Fetch current project name
  useEffect(() => {
    if (currentProjectId) {
      import('./lib/api').then(({ api }) => {
        api.getProject(currentProjectId).then((project) => {
          setCurrentProjectName(project.name);
        }).catch((err) => {
          console.error('Failed to fetch project:', err);
          setCurrentProjectName('');
        });
      });
    } else {
      setCurrentProjectName('');
    }
  }, [currentProjectId]);

  // Load default project on mount if none selected (only on Workspace page)
  useEffect(() => {
    // Only auto-load project on Workspace page, not on Projects page
    if (!currentProjectId && location.pathname === '/') {
      import('./lib/api').then(({ api }) => {
        api.getProjects(false).then((projects) => {
          if (projects.length > 0) {
            const defaultProjectId = projects[0].id;
            setCurrentProjectId(defaultProjectId);
            navigate(`/?project=${defaultProjectId}`, { replace: true });
          }
        }).catch(console.error);
      });
    }
  }, [currentProjectId, navigate, location.pathname]);

  // Save chat context to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('chatContext', JSON.stringify(chatContext));
  }, [chatContext]);

  // Keyboard shortcut for project switcher (Cmd/Ctrl + P)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'p') {
        e.preventDefault();
        setShowProjectSwitcher(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Request notification permissions on mount
  useEffect(() => {
    console.log('[App] Notification support:', desktopNotifications.isSupported());
    console.log('[App] Current permission:', desktopNotifications.getPermission());

    if (desktopNotifications.isSupported() && desktopNotifications.getPermission() === 'default') {
      console.log('[App] Requesting notification permission...');
      desktopNotifications.requestPermission()
        .then(granted => console.log('[App] Permission granted:', granted))
        .catch(err => console.error('[App] Permission error:', err));
    }
  }, []);

  // Build navigation items with dynamic paths
  const navItems = [
    {
      path: currentProjectId ? `/projects?project=${currentProjectId}` : '/projects',
      label: 'Projects',
      icon: FolderKanban
    },
    {
      path: currentProjectId ? `/?project=${currentProjectId}` : '/',
      label: 'Workspace',
      icon: Briefcase
    },
    { path: '/agents', label: 'Members', icon: Users },
    { path: '/skills', label: 'Skills', icon: BookOpen },
    { path: '/profile', label: 'Profile', icon: User },
  ];

  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col bg-gray-50">
        {/* Top Navigation - Desktop Only */}
        <nav className="hidden lg:block bg-white border-b-2 border-primary-500">
          <div className="px-4 py-2">
            <div className="flex items-center justify-between">
              {/* Logo - Left */}
              <div className="flex items-center gap-3">
                <img src="/logo.png" alt="kumiAI" className="w-12 h-12" />
                <h1 className="text-2xl font-semibold text-gray-900">kumiAI</h1>
              </div>

              {/* Project Name - Center */}
              <div className="absolute left-1/2 transform -translate-x-1/2">
                {currentProjectName && (
                  <h2 className="text-xl font-bold text-primary-600">{currentProjectName}</h2>
                )}
              </div>

              {/* Navigation Items - Right */}
              <div className="flex gap-1 items-center">
                {navItems.map((item, index) => {
                  const Icon = item.icon;
                  // Extract pathname from item.path (remove query params)
                  const itemPathname = item.path.split('?')[0];
                  // For Workspace, check if pathname is '/' (with or without query params)
                  // For other routes, check pathname match (ignoring query params)
                  const isActive = item.label === 'Workspace'
                    ? location.pathname === '/'
                    : location.pathname === itemPathname;
                  return (
                    <>
                      {/* Separator - before first item and between items */}
                      {index === 0 && (
                        <div className="h-8 w-0.5 bg-primary-500" />
                      )}
                      <Link
                        key={item.path}
                        to={item.path}
                        className={cn(
                          components.nav.item.base,
                          isActive ? components.nav.item.active : components.nav.item.inactive,
                          "px-2"
                        )}
                      >
                        <Icon className="w-4 h-4" />
                        <span>{item.label}</span>
                      </Link>
                      {/* Separator - not after last item */}
                      {index < navItems.length - 1 && (
                        <div className="h-8 w-0.5 bg-primary-500" />
                      )}
                    </>
                  );
                })}
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content Area - Add bottom padding on mobile for bottom nav */}
        <div className="flex-1 flex flex-col overflow-hidden pb-16 lg:pb-0">
          <Routes>
          <Route path="/" element={
            <WorkplaceKanban
              currentProjectId={currentProjectId}
              onChatContextChange={setChatContext}
              onProjectChange={(projectId) => {
                setCurrentProjectId(projectId);
                navigate(`/?project=${projectId}`, { replace: true });
              }}
            />
          } />
          <Route path="/projects" element={
            <Projects
              currentProjectId={currentProjectId}
              onProjectSelect={(projectId) => {
                setCurrentProjectId(projectId || undefined);
              }}
            />
          } />
          <Route path="/agents" element={
            <Agents
              onChatContextChange={setChatContext}
            />
          } />
          <Route path="/skills" element={
            <Skills
              onChatContextChange={setChatContext}
            />
          } />
          <Route path="/profile" element={
            <UserProfile />
          } />
          </Routes>
        </div>

        {/* Project Switcher Modal */}
        <ProjectSwitcher
          isOpen={showProjectSwitcher}
          onClose={() => setShowProjectSwitcher(false)}
          onSelectProject={(projectId) => {
            setCurrentProjectId(projectId);
            navigate(`/?project=${projectId}`);
          }}
          onCreateProject={() => {
            navigate('/projects');
          }}
          currentProjectId={currentProjectId}
        />

        {/* Bottom Navigation - Mobile Only */}
        <BottomNav />
      </div>
    </ErrorBoundary>
  );
}

export default App;
