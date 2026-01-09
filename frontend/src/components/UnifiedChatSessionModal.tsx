/**
 * UnifiedChatSessionModal Component
 *
 * Modal wrapper for orchestrator (multi-agent) sessions using UnifiedSessionChat.
 * Replaces ChatSessionModal with unified architecture.
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2 } from 'lucide-react';
import { UnifiedSessionChat } from './UnifiedSessionChat';
import { api, type AgentInstance, type AgentCharacter } from '../lib/api';

interface UnifiedChatSessionModalProps {
  agent: AgentInstance | null;
  characters: AgentCharacter[];
  onClose: () => void;
  inline?: boolean; // If true, render as inline component instead of modal
  onFilesCommitted?: () => void; // Callback when files are uploaded and committed
}

export function UnifiedChatSessionModal({
  agent,
  characters,
  onClose,
  inline = false,
  onFilesCommitted,
}: UnifiedChatSessionModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');

  // Update session status when agent changes
  useEffect(() => {
    if (!agent) {
      setSessionStatus('idle');
      setError(null);
      return;
    }

    setSessionStatus(agent.status || 'idle');

    // If session is in error state, set error message
    if (agent.status === 'error') {
      setError('Agent session encountered an error. Chat history is available in read-only mode.');
    } else {
      setError(null);
    }
  }, [agent?.instance_id, agent?.status]);

  // Handle Esc key to close modal
  useEffect(() => {
    if (!agent || inline) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [agent, onClose, inline]);

  if (!agent) return null;

  // Chat content component (shared between inline and modal)
  const chatContent = (
    <div
      className={`bg-white flex flex-col overflow-hidden max-w-full ${
        inline ? 'w-full h-full' : 'rounded-2xl border-2 border-primary-500 shadow-2xl w-full max-w-5xl h-[85vh]'
      }`}
      role="dialog"
      aria-label="Agent chat session"
    >
      {/* Error banner for sessions in error state */}
      {sessionStatus === 'error' && error && (
        <div className="flex-shrink-0 bg-red-50 border-b border-red-200 px-4 py-2 w-full max-w-full">
          <div className="flex items-start gap-2">
            <div className="w-5 h-5 mt-0.5 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
              <X className="w-3 h-3 text-red-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-red-900">Session Error</p>
              <p className="text-xs text-red-700 mt-0.5">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Chat Interface */}
      <div className="flex-1 overflow-hidden w-full max-w-full">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
              <p className="text-gray-500">Loading session...</p>
            </div>
          </div>
        ) : (
          <UnifiedSessionChat
            instanceId={agent.instance_id}
            role="orchestrator"
            className="h-full"
            readOnly={sessionStatus === 'error'}
            showHeader={true}
            onClose={onClose}
            onFilesCommitted={onFilesCommitted}
            initialSessionDescription={agent.current_session_description}
          />
        )}
      </div>
    </div>
  );

  // Render inline or as modal
  if (inline) {
    return chatContent;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          {chatContent}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
