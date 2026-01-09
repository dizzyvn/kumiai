/**
 * CharacterAssistantChat Component
 *
 * Character assistant chat interface using UnifiedSessionChat.
 * Replaces ChatWidget character_assistant functionality with unified architecture.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { User as UserIcon, X, Loader2 } from 'lucide-react';
import { UnifiedSessionChat } from './UnifiedSessionChat';
import { api } from '../lib/api';

interface CharacterAssistantChatProps {
  isOpen: boolean;
  onToggle: () => void;
  characterId?: string;
  characterPath?: string;
  characterName?: string;
  onCharacterUpdated?: () => void; // Callback when character is auto-saved
}

export function CharacterAssistantChat({
  isOpen,
  onToggle,
  characterId,
  characterPath,
  characterName,
  onCharacterUpdated,
}: CharacterAssistantChatProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');

  // Load or create character assistant session when character changes
  useEffect(() => {
    const loadOrCreateCharacterSession = async () => {
      if (!characterPath) {
        setSessionId(null);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        // Query for existing character assistant session (single persistent session)
        const sessions = await api.getSessions();
        const characterSession = sessions.find(
          (s) =>
            s.role === 'character_assistant' &&
            s.status !== 'cancelled' &&
            s.status !== 'error'
        );

        if (characterSession) {
          console.log('[CharacterAssistantChat] Found character session:', characterSession.instance_id, 'status:', characterSession.status);
          setSessionId(characterSession.instance_id);
          setSessionStatus(characterSession.status || 'idle');
        } else {
          // No session found, create one automatically at library root
          // Note: Backend overrides project_path to use settings.agents_dir
          console.log('[CharacterAssistantChat] No session found, creating new character assistant session');
          const newSession = await api.launchSession({
            team_member_ids: [],
            project_path: '', // Backend will override with settings.agents_dir
            session_description: 'Character Assistant - helps create/edit agent configurations',
            role: 'character_assistant',
            auto_start: false, // Don't auto-start, wait for user message
          });

          console.log('[CharacterAssistantChat] Created new character session:', newSession.instance_id);
          setSessionId(newSession.instance_id);
          setSessionStatus(newSession.status || 'idle');
        }
      } catch (err) {
        console.error('[CharacterAssistantChat] Failed to load/create character session:', err);
        setError(err instanceof Error ? err.message : 'Failed to load character assistant session');
      } finally {
        setIsLoading(false);
      }
    };

    loadOrCreateCharacterSession();
  }, [characterPath, characterId, characterName]);

  // Handle auto-save events
  const handleAutoSave = (type: 'skill' | 'character', id: string) => {
    console.log('[CharacterAssistantChat] Auto-save event:', type, id);
    if (type === 'character' && onCharacterUpdated) {
      onCharacterUpdated();
    }
  };

  // Handle character assistant recreation
  const handleRecreateCharacterAssistant = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Call API to recreate
      await api.recreateCharacterAssistant();
      console.log('[CharacterAssistantChat] Character assistant recreation initiated');

      // Poll for new session to finish initializing (max 60s, check every 2s)
      let attempts = 0;
      const maxAttempts = 30;
      const pollInterval = 2000;

      const pollForNewSession = async () => {
        attempts++;
        console.log(`[CharacterAssistantChat] Polling for new character assistant (attempt ${attempts}/${maxAttempts})...`);

        try {
          const sessions = await api.getSessions();
          const characterSession = sessions.find(
            s => s.role === 'character_assistant' && s.status !== 'cancelled'
          );

          if (characterSession) {
            console.log(`[CharacterAssistantChat] New character assistant status: ${characterSession.status}`);

            // Wait for initialization to complete
            if (characterSession.status !== 'initializing') {
              console.log(`[CharacterAssistantChat] Character assistant ready after ${attempts} attempts`);
              setSessionId(characterSession.instance_id);
              setSessionStatus(characterSession.status || 'idle');
              setIsLoading(false);
              return;
            }
          }
        } catch (error) {
          console.error('[CharacterAssistantChat] Error polling for new session:', error);
        }

        // Continue polling or timeout
        if (attempts < maxAttempts) {
          setTimeout(pollForNewSession, pollInterval);
        } else {
          console.warn('[CharacterAssistantChat] Polling timeout, stopping');
          setIsLoading(false);
          setError('Session recreation timed out. Please refresh the page.');
        }
      };

      // Start polling after 2s delay
      setTimeout(pollForNewSession, pollInterval);
    } catch (err) {
      console.error('[CharacterAssistantChat] Failed to recreate character assistant:', err);
      setError(err instanceof Error ? err.message : 'Failed to recreate character assistant');
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
            <p className="text-gray-500">Loading character assistant session...</p>
          </div>
        </div>
      ) : !sessionId ? (
        <div className="flex items-center justify-center h-full p-6">
          <div className="text-center max-w-sm">
            <UserIcon className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p className="text-sm text-gray-600">No character assistant session</p>
            <p className="text-xs text-gray-400 mt-2">
              {error || 'Select a character to start chatting with the assistant'}
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
              role="character_assistant"
              onClose={onToggle}
              className="h-full"
              readOnly={sessionStatus === 'error'}
              onAutoSave={handleAutoSave}
              onRecreateCharacterAssistant={handleRecreateCharacterAssistant}
              showHeader={true}
            />
          </div>
        </>
      )}
    </div>
  );
}
