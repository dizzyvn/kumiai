/**
 * useSessionMessages hook
 *
 * Manages message history and sending messages for a session.
 */

import { useEffect, useState, useCallback } from 'react';
import type { SessionMessage, SessionRole } from '../types/session';
import { filterMessagesByRole } from '../types/session';

interface UseSessionMessagesOptions {
  instanceId: string;
  role: SessionRole;
  autoLoad?: boolean;
}

interface UseSessionMessagesReturn {
  messages: SessionMessage[];
  filteredMessages: SessionMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  loadMessages: () => Promise<void>;
  clearMessages: () => void;
}

export function useSessionMessages({
  instanceId,
  role,
  autoLoad = true,
}: UseSessionMessagesOptions): UseSessionMessagesReturn {
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMessages = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const url = `/api/sessions/${instanceId}/messages`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to load messages: ${response.statusText}`);
      }

      const data = await response.json();
      setMessages(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load messages';
      setError(errorMessage);
      console.error('[useSessionMessages] Error loading messages:', err);
    } finally {
      setIsLoading(false);
    }
  }, [instanceId]);

  const sendMessage = useCallback(
    async (content: string) => {
      setError(null);

      try {
        const response = await fetch(`/api/sessions/${instanceId}/message`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            content,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to send message: ${response.statusText}`);
        }

        const result = await response.json();

        // Optimistically add user message to UI with temporary ID
        // This will be replaced when loadMessages() fetches from DB
        const userMessage: SessionMessage = {
          id: `temp-${Date.now()}`, // Temporary ID until DB version is loaded
          instance_id: instanceId,
          role: 'user',
          content,
          timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, userMessage]);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
        setError(errorMessage);
        console.error('[useSessionMessages] Error sending message:', err);
        throw err;
      }
    },
    [instanceId]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  // Auto-load messages on mount if enabled
  useEffect(() => {
    if (autoLoad) {
      loadMessages();
    }
  }, [autoLoad, loadMessages]);

  // Filter messages based on role
  const filtered = filterMessagesByRole(messages, role);

  // Sort by (timestamp, sequence) to preserve execution order
  // Messages with same timestamp are ordered by sequence number
  const filteredMessages = filtered.sort((a, b) => {
    const timeA = new Date(a.timestamp).getTime();
    const timeB = new Date(b.timestamp).getTime();

    if (timeA !== timeB) {
      return timeA - timeB; // Sort by timestamp first
    }

    // Same timestamp - sort by sequence
    return (a.sequence ?? 0) - (b.sequence ?? 0);
  });

  return {
    messages,
    filteredMessages,
    isLoading,
    error,
    sendMessage,
    loadMessages,
    clearMessages,
  };
}
