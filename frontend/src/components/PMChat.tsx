/**
 * PMChat Component
 *
 * PM (Project Manager) chat interface using UnifiedSessionChat.
 * Replaces ChatWidget PM functionality with unified architecture.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Briefcase, X, Loader2 } from 'lucide-react';
import { UnifiedSessionChat } from './UnifiedSessionChat';
import { api } from '../lib/api';

interface PMChatProps {
  isOpen: boolean;
  onToggle: () => void;
  projectId: string;
  projectPath?: string;
  projectName?: string;
  onSessionJump?: (sessionId: string) => void;
}

export function PMChat({ isOpen, onToggle, projectId, projectPath, projectName, onSessionJump }: PMChatProps) {
  const [pmInstanceId, setPmInstanceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');

  // Load or create PM session when project changes
  useEffect(() => {
    const loadPMSession = async () => {
      if (!projectId || !projectPath) {
        setPmInstanceId(null);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        // Query for existing PM session for this project (include all statuses)
        const sessions = await api.getSessions();

        // Find all PM sessions for this project
        const pmSessions = sessions.filter(
          (s) => s.role === 'pm' && s.project_id === projectId
        );

        // Warn about duplicates
        if (pmSessions.length > 1) {
          console.warn(`[PMChat] Found ${pmSessions.length} PM sessions for project ${projectId}. Using the last one. Duplicates:`,
            pmSessions.map(s => ({ id: s.instance_id, status: s.status }))
          );
        }

        // If multiple PM sessions exist, use the most recent one (or last in array)
        // This matches Projects page behavior where Map.set overwrites with last session
        const pmSession = pmSessions.length > 0 ? pmSessions[pmSessions.length - 1] : null;

        if (pmSession) {
          console.log('[PMChat] Found PM session:', pmSession.instance_id, 'status:', pmSession.status);

          // Treat cancelled sessions as idle (they're ready to use again)
          const effectiveStatus = pmSession.status === 'cancelled' ? 'idle' : pmSession.status;

          setPmInstanceId(pmSession.instance_id);
          setSessionStatus(effectiveStatus || 'idle');

          // If session is in error state, set error message
          if (pmSession.status === 'error') {
            setError('PM session encountered an error. Chat history is available in read-only mode.');
          }
        } else {
          console.log('[PMChat] No PM session found for project', projectId);
          // PM session should have been created when project was created
          // If not found, there might be an issue
          setError('No PM session found. Try refreshing the page.');
        }
      } catch (err) {
        console.error('[PMChat] Failed to load PM session:', err);
        setError(err instanceof Error ? err.message : 'Failed to load PM session');
      } finally {
        setIsLoading(false);
      }
    };

    loadPMSession();
  }, [projectId, projectPath]);

  return (
    <motion.div
      initial={false}
      animate={{ width: isOpen ? 400: 0 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className="h-full flex flex-col overflow-hidden bg-white"
    >
      {/* Chat Toggle Button (floating) */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="fixed bottom-20 lg:bottom-6 right-6 w-14 h-14 bg-white border border-gray-200 hover:bg-gray-50 rounded-full shadow-md flex items-center justify-center transition-colors z-50"
          aria-label="Open PM chat"
          title="Talk to your Project Manager"
        >
          <Briefcase className="w-6 h-6 text-gray-600" />
        </button>
      )}

      {isOpen && (
        <div className="flex flex-col h-full">
          {/* Chat Content */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {isLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                  <p className="text-gray-500">Loading PM session...</p>
                </div>
              </div>
            ) : !pmInstanceId ? (
              <div className="flex items-center justify-center h-full p-6">
                <div className="text-center max-w-sm">
                  <Briefcase className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                  <p className="text-sm text-gray-600">No PM session available</p>
                  <p className="text-xs text-gray-400 mt-2">
                    {error || 'Select a project with a PM to start chatting'}
                  </p>
                </div>
              </div>
            ) : (
              <>
                {/* Error banner for sessions in error state */}
                {sessionStatus === 'error' && (
                  <div className="flex-shrink-0 bg-red-50 border-b border-red-200 px-4 py-2">
                    <div className="flex items-start gap-2">
                      <div className="w-5 h-5 mt-0.5 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
                        <X className="w-3 h-3 text-red-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-red-900">Session Error</p>
                        <p className="text-xs text-red-700 mt-0.5">
                          {error || 'This session encountered an error. Chat history is read-only.'}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Chat interface */}
                <div className="flex-1 overflow-hidden">
                  <UnifiedSessionChat
                    instanceId={pmInstanceId}
                    role="pm"
                    className="h-full"
                    readOnly={sessionStatus === 'error'}
                    showHeader={true}
                    onClose={onToggle}
                    onSessionJump={onSessionJump}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
