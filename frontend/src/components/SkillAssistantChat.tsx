/**
 * SkillAssistantChat Component
 *
 * Skill assistant chat interface using UnifiedSessionChat.
 * Replaces ChatWidget skill_assistant functionality with unified architecture.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Wrench, X, Loader2 } from 'lucide-react';
import { UnifiedSessionChat } from './UnifiedSessionChat';
import { api } from '../lib/api';

interface SkillAssistantChatProps {
  isOpen: boolean;
  onToggle: () => void;
  skillId?: string;
  skillName?: string;
  onSkillUpdated?: () => void; // Callback when skill is auto-saved
}

export function SkillAssistantChat({
  isOpen,
  onToggle,
  skillId,
  skillName,
  onSkillUpdated,
}: SkillAssistantChatProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');

  // Load or create skill assistant session when component mounts
  useEffect(() => {
    const loadOrCreateSkillSession = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Query for existing skill assistant session (single persistent session)
        const sessions = await api.getSessions();
        const skillSession = sessions.find(
          (s) =>
            s.role === 'skill_assistant' &&
            s.status !== 'cancelled' &&
            s.status !== 'error'
        );

        if (skillSession) {
          console.log('[SkillAssistantChat] Found skill session:', skillSession.instance_id, 'status:', skillSession.status);
          setSessionId(skillSession.instance_id);
          setSessionStatus(skillSession.status || 'idle');
        } else {
          // No session found, create one automatically at library root
          // Note: Backend overrides project_path to use settings.skills_dir
          console.log('[SkillAssistantChat] No session found, creating new skill assistant session');
          const newSession = await api.launchSession({
            team_member_ids: [],
            project_path: '', // Backend will override with settings.skills_dir
            session_description: 'Skill Assistant - helps create/edit skill definitions',
            role: 'skill_assistant',
            auto_start: false, // Don't auto-start, wait for user message
          });

          console.log('[SkillAssistantChat] Created new skill session:', newSession.instance_id);
          setSessionId(newSession.instance_id);
          setSessionStatus(newSession.status || 'idle');
        }
      } catch (err) {
        console.error('[SkillAssistantChat] Failed to load/create skill session:', err);
        setError(err instanceof Error ? err.message : 'Failed to load skill assistant session');
      } finally {
        setIsLoading(false);
      }
    };

    loadOrCreateSkillSession();
  }, []); // Load once on mount

  // Handle auto-save events
  const handleAutoSave = (type: 'skill' | 'character', id: string) => {
    console.log('[SkillAssistantChat] Auto-save event:', type, id);
    if (type === 'skill' && onSkillUpdated) {
      onSkillUpdated();
    }
  };

  // Handle skill assistant recreation
  const handleRecreateSkillAssistant = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Call API to recreate
      await api.recreateSkillAssistant();
      console.log('[SkillAssistantChat] Skill assistant recreation initiated');

      // Poll for new session to finish initializing (max 60s, check every 2s)
      let attempts = 0;
      const maxAttempts = 30;
      const pollInterval = 2000;

      const pollForNewSession = async () => {
        attempts++;
        console.log(`[SkillAssistantChat] Polling for new skill assistant (attempt ${attempts}/${maxAttempts})...`);

        try {
          const sessions = await api.getSessions();
          const skillSession = sessions.find(
            s => s.role === 'skill_assistant' && s.status !== 'cancelled'
          );

          if (skillSession) {
            console.log(`[SkillAssistantChat] New skill assistant status: ${skillSession.status}`);

            // Wait for initialization to complete
            if (skillSession.status !== 'initializing') {
              console.log(`[SkillAssistantChat] Skill assistant ready after ${attempts} attempts`);
              setSessionId(skillSession.instance_id);
              setSessionStatus(skillSession.status || 'idle');
              setIsLoading(false);
              return;
            }
          }
        } catch (error) {
          console.error('[SkillAssistantChat] Error polling for new session:', error);
        }

        // Continue polling or timeout
        if (attempts < maxAttempts) {
          setTimeout(pollForNewSession, pollInterval);
        } else {
          console.warn('[SkillAssistantChat] Polling timeout, stopping');
          setIsLoading(false);
          setError('Session recreation timed out. Please refresh the page.');
        }
      };

      // Start polling after 2s delay
      setTimeout(pollForNewSession, pollInterval);
    } catch (err) {
      console.error('[SkillAssistantChat] Failed to recreate skill assistant:', err);
      setError(err instanceof Error ? err.message : 'Failed to recreate skill assistant');
      setIsLoading(false);
    }
  };

  // Mobile: full screen, Desktop: fills the detail panel area
  // Note: The floating toggle button is rendered by the parent page
  if (!isOpen) {
    return null;
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
            <p className="text-gray-500">Loading skill assistant session...</p>
          </div>
        </div>
      ) : !sessionId ? (
        <div className="flex items-center justify-center h-full p-6">
          <div className="text-center max-w-sm">
            <Wrench className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p className="text-sm text-gray-600">No skill assistant session</p>
            <p className="text-xs text-gray-400 mt-2">
              {error || 'Select a skill to start chatting with the assistant'}
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
                    This session encountered an error. Chat history is read-only.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Chat interface */}
          <div className="flex-1 overflow-hidden">
            <UnifiedSessionChat
              instanceId={sessionId}
              role="skill_assistant"
              onClose={onToggle}
              className="h-full"
              readOnly={sessionStatus === 'error'}
              onAutoSave={handleAutoSave}
              onRecreateSkillAssistant={handleRecreateSkillAssistant}
              showHeader={true}
            />
          </div>
        </>
      )}
    </div>
  );
}
