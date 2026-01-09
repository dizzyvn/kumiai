/**
 * UnifiedSessionChat component
 *
 * Single chat component that handles all session types (orchestrator, PM, skill assistant, character assistant).
 * Replaces ChatSessionModal and ChatWidget with role-aware rendering.
 *
 * Features Tufte-inspired design with:
 * - Avatar display for all speakers
 * - Markdown rendering with proper typography
 * - Tool marker badges
 * - Typing indicators
 * - Running indicator and interrupt button
 */

import React, { useState, useEffect, useRef, useCallback, useReducer } from 'react';
import { Send, X, Loader2, AlertCircle, StopCircle, Wrench, Users, Briefcase, User as UserIcon, ArrowDown, Target, Paperclip, MoreVertical, RefreshCw } from 'lucide-react';
import { useSessionStream } from '../hooks/useSessionStream';
import { useSessionMessages } from '../hooks/useSessionMessages';
import { useFileUpload } from '../hooks/useFileUpload';
import { MessageBubble } from './MessageBubble';
import { MessageGroup } from './MessageGroup';
import { Avatar } from './Avatar';
import { FileAttachmentPreview } from './FileAttachmentPreview';
import { api, type AgentCharacter } from '../lib/api';
import type { SessionRole, SessionEvent, AutoSaveEvent, SessionMessage, UserNotificationEvent } from '../types/session';
import { getRoleConfig } from '../types/session';
import { FileContextProvider } from '@/contexts/FileContext';
import { cn } from '@/lib/utils';
import { desktopNotifications } from '../lib/notifications';

// Streaming message reducer for atomic updates
type StreamingMessageAction =
  | { type: 'APPEND_DELTA'; payload: { content: string; instanceId: string; eventId?: string } }
  | { type: 'MARK_COMPLETE' }
  | { type: 'CLEAR' }
  | { type: 'INIT'; payload: { content: string; instanceId: string; eventId?: string } };

interface StreamingMessageState {
  message: SessionMessage | null;
  processedEventIds: Set<string>; // Track processed event IDs for deduplication
}

function streamingMessageReducer(
  state: StreamingMessageState,
  action: StreamingMessageAction
): StreamingMessageState {
  switch (action.type) {
    case 'INIT':
      // Track event ID if provided
      const initEventId = action.payload.eventId;
      const newProcessedIds = initEventId
        ? new Set([...state.processedEventIds, initEventId])
        : state.processedEventIds;

      return {
        message: {
          instance_id: action.payload.instanceId,
          role: 'assistant',
          content: action.payload.content,
          timestamp: new Date().toISOString(),
          isStreaming: true,
        } as SessionMessage,
        processedEventIds: newProcessedIds,
      };

    case 'APPEND_DELTA':
      // Check for duplicate event
      const deltaEventId = action.payload.eventId;
      if (deltaEventId && state.processedEventIds.has(deltaEventId)) {
        console.log(`[UnifiedSessionChat] Skipping duplicate event: ${deltaEventId}`);
        return state; // Skip this delta, already processed
      }

      if (!state.message) {
        // Initialize if no message exists
        const newProcessedIds = deltaEventId
          ? new Set([...state.processedEventIds, deltaEventId])
          : state.processedEventIds;

        return {
          message: {
            instance_id: action.payload.instanceId,
            role: 'assistant',
            content: action.payload.content,
            timestamp: new Date().toISOString(),
            isStreaming: true,
          } as SessionMessage,
          processedEventIds: newProcessedIds,
        };
      }

      // Append to existing message and track event ID
      const updatedProcessedIds = deltaEventId
        ? new Set([...state.processedEventIds, deltaEventId])
        : state.processedEventIds;

      return {
        message: {
          ...state.message,
          content: state.message.content + action.payload.content,
        },
        processedEventIds: updatedProcessedIds,
      };

    case 'MARK_COMPLETE':
      if (!state.message) return state;
      return {
        ...state,
        message: {
          ...state.message,
          isStreaming: false,
        },
      };

    case 'CLEAR':
      return {
        message: null,
        processedEventIds: new Set(),
      };

    default:
      return state;
  }
}

interface UnifiedSessionChatProps {
  instanceId: string;
  role: SessionRole;
  onClose?: () => void;
  onAutoSave?: (type: 'skill' | 'character', id: string) => void;
  onSessionJump?: (sessionId: string) => void; // Callback when user clicks to jump to a session
  onFilesCommitted?: () => void; // Callback when files are uploaded and committed to session
  onRecreatePm?: (projectId: string) => Promise<void>; // Callback when user requests PM recreation
  onRecreateSkillAssistant?: () => Promise<void>; // Callback when user requests skill assistant recreation
  onRecreateCharacterAssistant?: () => Promise<void>; // Callback when user requests character assistant recreation
  className?: string;
  readOnly?: boolean;
  showHeader?: boolean; // Whether to show the header (default: true)
  initialSessionDescription?: string; // Session description to show immediately (avoids refetch delay)
}

export const UnifiedSessionChat: React.FC<UnifiedSessionChatProps> = ({
  instanceId,
  role,
  onClose,
  onAutoSave,
  onSessionJump,
  onFilesCommitted,
  onRecreatePm,
  onRecreateSkillAssistant,
  onRecreateCharacterAssistant,
  className = '',
  readOnly = false,
  showHeader = true,
  initialSessionDescription,
}) => {
  const [input, setInput] = useState('');
  const [typingAgents, setTypingAgents] = useState<Set<string>>(new Set());
  const [streamingState, dispatchStreaming] = useReducer(streamingMessageReducer, {
    message: null,
    processedEventIds: new Set(),
  });
  const [characters, setCharacters] = useState<AgentCharacter[]>([]);
  const [charactersLoading, setCharactersLoading] = useState(true); // Track character loading state
  const [userAvatar, setUserAvatar] = useState<string | undefined>(undefined); // User profile avatar
  const [sessionData, setSessionData] = useState<any>(
    initialSessionDescription ? { current_session_description: initialSessionDescription } : null
  );
  const [isCancelled, setIsCancelled] = useState(false); // Flag to ignore events after cancellation
  const [queueSize, setQueueSize] = useState(0); // Message queue count
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [isRecreatingPm, setIsRecreatingPm] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const roleConfig = getRoleConfig(role);

  // File upload hook
  const {
    attachedFiles,
    addFiles,
    removeFile,
    commitFiles,
    hasFiles,
    hasPreparedFiles
  } = useFileUpload(instanceId);

  // Content validation constants
  const MAX_MESSAGE_LENGTH = 100_000; // 100KB max per message
  const MAX_DELTA_LENGTH = 10_000; // 10KB max per delta

  // Sanitize and validate content before adding to state
  const sanitizeContent = useCallback((content: string, maxLength: number = MAX_DELTA_LENGTH): string => {
    if (!content) return '';

    // Truncate if too long
    if (content.length > maxLength) {
      console.warn(`[UnifiedSessionChat] Content truncated from ${content.length} to ${maxLength} chars`);
      return content.substring(0, maxLength) + '\n[... content truncated due to size]';
    }

    return content;
  }, []);

  // Load characters, user profile, and session data
  useEffect(() => {
    let mounted = true;
    setCharactersLoading(true);

    Promise.all([
      api.getCharacters(),
      api.getSessions(),
      api.getUserProfile()
    ])
      .then(([chars, sessions, profile]) => {
        if (!mounted) return;

        setCharacters(chars);
        const session = sessions.find(s => s.instance_id === instanceId);
        if (session) {
          setSessionData(session);
        }
        // Set user avatar if available
        if (profile.avatar) {
          setUserAvatar(profile.avatar);
        }
        setCharactersLoading(false);
      })
      .catch((error) => {
        console.error('[UnifiedSessionChat] Failed to load session data:', error);
        setCharactersLoading(false); // Still set to false on error to prevent infinite loading
      });

    return () => {
      mounted = false;
    };
  }, [instanceId]);

  const {
    filteredMessages,
    isLoading: messagesLoading,
    error: messagesError,
    sendMessage,
    loadMessages,
  } = useSessionMessages({
    instanceId,
    role,
    autoLoad: true,
  });

  // Handle SSE events - wrapped in useCallback to prevent reconnections
  const handleEvent = useCallback((event: SessionEvent) => {
    console.log('[🔍 DEBUG] Event received:', event.type, 'content:', (event as any).content?.substring(0, 50));

    // Ignore streaming events if session was cancelled
    // This prevents late buffered events from recreating streamingMessage after cancellation
    if (isCancelled && ['stream_delta', 'tool_use', 'tool_complete', 'message_complete'].includes(event.type)) {
      console.log('[UnifiedSessionChat] Ignoring', event.type, 'event after cancellation');
      return;
    }

    switch (event.type) {
      case 'stream_delta':
        // Accumulate streaming content with validation
        const sanitizedDelta = sanitizeContent(event.content, MAX_DELTA_LENGTH);

        // Check message size limit before appending
        if (streamingState.message) {
          const newContentLength = streamingState.message.content.length + sanitizedDelta.length;
          if (newContentLength > MAX_MESSAGE_LENGTH) {
            console.warn(`[UnifiedSessionChat] Message size limit reached (${newContentLength} > ${MAX_MESSAGE_LENGTH})`);
            dispatchStreaming({
              type: 'APPEND_DELTA',
              payload: {
                content: '\n[... message size limit reached, truncating further content]',
                instanceId,
                eventId: event.event_id,
              },
            });
            dispatchStreaming({ type: 'MARK_COMPLETE' });
            break;
          }
        }

        dispatchStreaming({
          type: 'APPEND_DELTA',
          payload: {
            content: sanitizedDelta,
            instanceId,
            eventId: event.event_id, // Pass event_id for deduplication
          },
        });
        break;

      case 'tool_use':
        // Tool started - will be persisted by backend when complete
        console.log('[UnifiedSessionChat] Tool use event:', event.toolName);
        break;

      case 'tool_complete':
        // Tool completed and saved to database - clear streaming state and reload
        // Clearing prevents duplicate messages (streaming + DB versions)
        console.log('[UnifiedSessionChat] Tool complete event:', event.toolName);
        dispatchStreaming({ type: 'CLEAR' });
        loadMessages().catch((err) => {
          console.error('[UnifiedSessionChat] Failed to reload messages after tool_complete:', err);
        });
        break;

      case 'agent_started':
      case 'agent_agent_started':
        // Add typing indicator for specialist
        if (event.agentName) {
          setTypingAgents((prev) => new Set(prev).add(event.agentName!));
        }
        break;

      case 'agent_delta':
      case 'agent_agent_delta':
        // Specialist streaming - content handled by backend
        break;

      case 'agent_response_complete':
      case 'agent_agent_response_complete':
        // Remove typing indicator for specialist
        if (event.agentName) {
          setTypingAgents((prev) => {
            const next = new Set(prev);
            next.delete(event.agentName!);
            return next;
          });
        }
        break;

      case 'message_complete':
        // Mark streaming message as complete but keep it visible
        dispatchStreaming({ type: 'MARK_COMPLETE' });
        break;

      case 'result':
        // Execution complete, reload messages from database
        dispatchStreaming({ type: 'CLEAR' });
        loadMessages().catch((err) => {
          console.error('[UnifiedSessionChat] loadMessages() failed:', err);
        });
        break;

      case 'auto_save':
        // Auto-save occurred (for assistants)
        const autoSaveEvent = event as AutoSaveEvent;
        if (onAutoSave) {
          onAutoSave(autoSaveEvent.auto_save_type, autoSaveEvent.item_id);
        }
        break;

      case 'error':
        console.error('[UnifiedSessionChat] Error event:', event.error);
        dispatchStreaming({ type: 'CLEAR' });
        break;

      case 'cancelled':
        console.log('[UnifiedSessionChat] Session cancelled');
        // Set cancellation flag to ignore late buffered events
        setIsCancelled(true);
        // Clear streaming state and reload messages from database
        dispatchStreaming({ type: 'CLEAR' });
        setTypingAgents(new Set());
        loadMessages().catch((err) => {
          console.error('[UnifiedSessionChat] Failed to reload messages after cancel:', err);
        });
        break;

      case 'user_notification':
        // PM agent sent a desktop notification
        const notificationEvent = event as UserNotificationEvent;
        console.log('[UnifiedSessionChat] 🔔 User notification received:', {
          title: notificationEvent.title,
          message: notificationEvent.message,
          project_name: notificationEvent.project_name,
          priority: notificationEvent.priority,
          permission: desktopNotifications.getPermission(),
          isSupported: desktopNotifications.isSupported()
        });

        const notification = desktopNotifications.show({
          title: notificationEvent.title,
          message: notificationEvent.message,
          project_name: notificationEvent.project_name,
          priority: notificationEvent.priority || 'normal'
        });

        if (notification) {
          console.log('[UnifiedSessionChat] ✓ Notification shown successfully');
        } else {
          console.warn('[UnifiedSessionChat] ✗ Failed to show notification');
        }
        break;
    }
  }, [instanceId, loadMessages, onAutoSave, sanitizeContent, MAX_DELTA_LENGTH, MAX_MESSAGE_LENGTH, isCancelled, streamingState.message]);

  // Use unified hooks - called after handleEvent is defined
  const { status, isConnected, error: streamError, events } = useSessionStream({
    instanceId,
    role,
    onEvent: handleEvent,
  });

  // Poll queue status when session is processing
  useEffect(() => {
    if (status === 'working') {
      const pollQueueStatus = async () => {
        try {
          const response = await fetch(`/api/sessions/${instanceId}/queue-status`);
          if (response.ok) {
            const data = await response.json();
            setQueueSize(data.queue_size || 0);
          }
        } catch (error) {
          console.error('[UnifiedSessionChat] Failed to fetch queue status:', error);
        }
      };

      // Poll immediately and then every second
      pollQueueStatus();
      const interval = setInterval(pollQueueStatus, 1000);
      return () => clearInterval(interval);
    } else {
      // Clear queue size when not processing
      setQueueSize(0);
    }
  }, [status, instanceId]);

  // Check if user is near bottom of scroll container
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const threshold = 100; // pixels from bottom
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold;

    setShouldAutoScroll(isNearBottom);
    setShowScrollButton(!isNearBottom);
  }, []);

  // Auto-scroll to bottom only if user is at bottom
  useEffect(() => {
    // Only auto-scroll if user is at the bottom
    if (shouldAutoScroll) {
      // Use instant scroll to avoid jumping animation
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [filteredMessages, streamingState.message, typingAgents, shouldAutoScroll]);

  // Scroll to bottom handler for the button
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setShouldAutoScroll(true);
    setShowScrollButton(false);
  }, []);

  // Drag-and-drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length > 0) {
      await addFiles(droppedFiles);
    }
  }, [addFiles]);

  // File selection handler
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      await addFiles(selectedFiles);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [addFiles]);

  const handleSendMessage = async () => {
    // Allow sending while processing (messages will be queued)
    // Only block if there's nothing to send
    if (!input.trim() && !hasFiles) return;

    let messageToSend = input;
    let filesWereCommitted = false;

    // Commit files and append metadata to message
    if (hasFiles) {
      try {
        const fileMetadata = await commitFiles('working');
        messageToSend = messageToSend.trim() + fileMetadata;
        filesWereCommitted = true;
      } catch (error) {
        console.error('Failed to commit files:', error);
        return; // Don't send message if file commit fails
      }
    }

    // Convert single line breaks to double line breaks for proper Markdown rendering
    // This ensures single newlines in the input show as paragraph breaks in rendered output
    messageToSend = messageToSend.replace(/\n/g, '\n\n');

    setInput('');
    setShouldAutoScroll(true); // Always scroll to bottom when sending a message

    // Keep focus in the input box for the next message
    textareaRef.current?.focus();

    // Reset cancellation flag when starting a new query
    console.log('[🔍 DEBUG] Sending new message, clearing streamingMessage and resetting isCancelled');
    console.log('[🔍 DEBUG] Current streamingMessage:', streamingState.message);
    setIsCancelled(false);
    dispatchStreaming({ type: 'CLEAR' }); // Explicitly clear any stale streaming message

    const message = messageToSend;

    try {
      await sendMessage(message);

      // Notify parent to refresh file explorer if files were committed
      if (filesWereCommitted && onFilesCommitted) {
        onFilesCommitted();
      }
    } catch (err) {
      console.error('[UnifiedSessionChat] Failed to send message:', err);
    }
  };

  const handleInterrupt = async () => {
    try {
      await api.cancelSession(instanceId);
      dispatchStreaming({ type: 'CLEAR' });
      setTypingAgents(new Set());
    } catch (err) {
      console.error('[UnifiedSessionChat] Failed to interrupt:', err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Don't send message if user is composing (e.g., typing in Vietnamese/Japanese)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCompositionStart = () => {
    setIsComposing(true);
  };

  const handleCompositionEnd = () => {
    setIsComposing(false);
  };

  const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles: File[] = [];

    // Extract image files from clipboard
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          imageFiles.push(file);
        }
      }
    }

    // If images found, prevent default paste and add as files
    if (imageFiles.length > 0) {
      e.preventDefault();
      await addFiles(imageFiles);
    }
    // If no images, allow default text paste behavior
  }, [addFiles]);

  const handleRecreatePm = async () => {
    if (!sessionData?.project_id) {
      console.error('[UnifiedSessionChat] No project_id found for PM session');
      return;
    }

    if (!confirm('This will recreate the PM session. All conversation history will be lost. Continue?')) {
      return;
    }

    setIsRecreatingPm(true);
    setShowDropdown(false);

    try {
      // Use parent's handler if available (includes polling logic)
      if (onRecreatePm) {
        await onRecreatePm(sessionData.project_id);
      } else {
        // Fallback: direct API call (parent will need to handle reload)
        await api.recreatePmSession(sessionData.project_id);
        console.log('[UnifiedSessionChat] PM session recreation initiated (no callback provided)');
      }
    } catch (err) {
      console.error('[UnifiedSessionChat] Failed to recreate PM session:', err);
      alert('Failed to recreate PM session. See console for details.');
    } finally {
      setIsRecreatingPm(false);
    }
  };

  const handleRecreateSkillAssistant = async () => {
    if (!confirm('This will recreate the skill assistant session. All conversation history will be lost. Continue?')) {
      return;
    }

    setIsRecreatingPm(true); // Reuse same loading state
    setShowDropdown(false);

    try {
      // Use parent's handler if available (includes polling logic)
      if (onRecreateSkillAssistant) {
        await onRecreateSkillAssistant();
      } else {
        // Fallback: direct API call
        await api.recreateSkillAssistant();
        console.log('[UnifiedSessionChat] Skill assistant recreation initiated (no callback provided)');
      }
    } catch (err) {
      console.error('[UnifiedSessionChat] Failed to recreate skill assistant:', err);
      alert('Failed to recreate skill assistant. See console for details.');
    } finally {
      setIsRecreatingPm(false);
    }
  };

  const handleRecreateCharacterAssistant = async () => {
    if (!confirm('This will recreate the character assistant session. All conversation history will be lost. Continue?')) {
      return;
    }

    setIsRecreatingPm(true); // Reuse same loading state
    setShowDropdown(false);

    try {
      // Use parent's handler if available (includes polling logic)
      if (onRecreateCharacterAssistant) {
        await onRecreateCharacterAssistant();
      } else {
        // Fallback: direct API call
        await api.recreateCharacterAssistant();
        console.log('[UnifiedSessionChat] Character assistant recreation initiated (no callback provided)');
      }
    } catch (err) {
      console.error('[UnifiedSessionChat] Failed to recreate character assistant:', err);
      alert('Failed to recreate character assistant. See console for details.');
    } finally {
      setIsRecreatingPm(false);
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showDropdown]);

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';
    // Set height to scrollHeight (content height)
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [input]);

  // Render icon based on role
  const RoleIcon = getRoleIcon(role);

  // Get character info for avatar display - use same lookup logic as MessageBubble
  // Look up character from characters array to ensure consistency with message bubbles
  let agentColor = '#4A90E2';
  let agentAvatar = 'default';

  // Try to find character ID from either character_id or character.id
  const lookupCharacterId = sessionData?.character_id || sessionData?.character?.id;

  if (lookupCharacterId) {
    // Look up from characters array using the same logic as MessageBubble
    const character = characters.find(c =>
      c.id === lookupCharacterId || c.name === lookupCharacterId
    );
    if (character) {
      // Use same fallback as MessageBubble: character.avatar || character.id
      agentColor = character.color || '#4A90E2';
      agentAvatar = character.avatar || character.id || 'default-avatar';
    } else {
      // Fallback if character not found in array
      agentColor = sessionData?.character?.color || '#4A90E2';
      agentAvatar = sessionData?.character?.id || 'default-avatar';
    }
  }

  // Check if session is running based on:
  // 1. Session status is 'working' (SSE status_change events)
  // 2. There's an incomplete streaming message in the database (is_streaming=true)
  // 3. There's a local streaming message being built (streamingState.message with isStreaming)
  const hasStreamingMessage = filteredMessages.some(msg => msg.is_streaming) ||
                              (streamingState.message?.isStreaming === true);
  const isProcessing = status === 'working' || hasStreamingMessage;

  return (
    <FileContextProvider contextType="session" contextId={instanceId}>
      <div className={`flex flex-col h-full w-full max-w-full bg-white ${className}`}>
      {/* Header */}
      {showHeader && (
            <div className={cn(
              "h-12 px-2 lg:px-3 mb-4 border-b-2 border-primary-500 flex items-center w-full max-w-full flex-shrink-0",
              role === 'pm'
                ? "bg-primary-500"
                : "bg-primary-100"
            )}>
              <div className="flex items-center justify-between gap-4 w-full">
                {/* Left: Role indicator */}
                <div className="flex-1 min-w-0 flex items-center gap-2">
                  <RoleIcon className={cn(
                    "w-4 h-4 flex-shrink-0",
                    role === 'pm' ? "text-white" : "text-primary-700"
                  )} />
                  <h3 className={cn(
                    "text-base font-medium truncate",
                    role === 'pm' ? "text-white" : "text-primary-900"
                  )}>
                    {/* For orchestrator, use session description; for others, use role display name */}
                    {role === 'orchestrator' && sessionData?.current_session_description
                      ? sessionData.current_session_description
                      : roleConfig.displayName}
                  </h3>
                  {/* Connection Status Indicator */}
                  {streamError ? (
                    // Red dot for connection lost
                    <div className="flex items-center gap-1 text-xs text-red-600" title="Connection lost">
                      <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                    </div>
                  ) : isConnected ? (
                    // Green pulsing dot for connected
                    <div className="flex items-center gap-1 text-xs text-green-600" title="Connected">
                      <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    </div>
                  ) : (
                    // Gray dot for idle/not connected
                    <div className="flex items-center gap-1 text-xs text-gray-400" title="Idle">
                      <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
                    </div>
                  )}
                </div>

                {/* Right: Status and Actions */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  {/* Processing Indicator */}
                  {isProcessing && (
                    <Loader2 className={cn(
                      "w-5 h-5 animate-spin",
                      role === 'pm' ? "text-white" : "text-primary-600"
                    )} />
                  )}

                  {/* Interrupt Button */}
                  {isProcessing && !readOnly && (
                    <button
                      onClick={handleInterrupt}
                      className={cn(
                        "p-1.5 rounded transition-colors",
                        role === 'pm'
                          ? "hover:bg-primary-600 text-white hover:text-white"
                          : "hover:bg-primary-200 text-primary-700 hover:text-primary-900"
                      )}
                      title="Interrupt current execution"
                    >
                      <StopCircle className="w-5 h-5" />
                    </button>
                  )}

                  {/* Agent Avatars */}
                  {sessionData && (
                    <div className="flex items-center -space-x-2">
                      {/* Main character avatar - use looked up values */}
                      {(sessionData.character_id || sessionData.character) && (
                        <Avatar
                          seed={agentAvatar}
                          size={32}
                          className="w-8 h-8 rounded-full border-2 border-white shadow-sm"
                          color={agentColor}
                        />
                      )}

                      {/* Specialist avatars for orchestrator */}
                      {sessionData.selected_specialists && sessionData.selected_specialists.length > 0 && (
                        sessionData.selected_specialists.slice(0, 3).map((specialistId: string) => {
                          const specialist = characters.find(c => c.id === specialistId);
                          return (
                            <Avatar
                              key={specialistId}
                              seed={specialist?.avatar || specialist?.id || specialistId}
                              size={32}
                              className="w-8 h-8 rounded-full border-2 border-white shadow-sm"
                              color={specialist?.color || '#4A90E2'}
                            />
                          );
                        })
                      )}

                      {/* Show "+N" if more than 3 specialists */}
                      {sessionData.selected_specialists && sessionData.selected_specialists.length > 3 && (
                        <div
                          className="w-8 h-8 rounded-full flex items-center justify-center bg-gray-300 text-gray-700 text-xs font-medium border-2 border-white shadow-sm"
                          title={`+${sessionData.selected_specialists.length - 3} more specialists`}
                        >
                          +{sessionData.selected_specialists.length - 3}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Dropdown Menu (PM, Skill Assistant, and Character Assistant) */}
                  {(role === 'pm' || role === 'skill_assistant' || role === 'character_assistant') && (
                    <div className="relative" ref={dropdownRef}>
                      <button
                        onClick={() => setShowDropdown(!showDropdown)}
                        className={cn(
                          "p-1.5 rounded transition-colors",
                          role === 'pm'
                            ? "hover:bg-primary-600 text-white"
                            : "hover:bg-primary-200 text-primary-700"
                        )}
                        aria-label="Options"
                        disabled={isRecreatingPm}
                      >
                        {isRecreatingPm ? (
                          <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                          <MoreVertical className="w-5 h-5" />
                        )}
                      </button>

                      {/* Dropdown Menu */}
                      {showDropdown && (
                        <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg border border-gray-200 z-50">
                          <div className="py-1">
                            <button
                              onClick={
                                role === 'pm'
                                  ? handleRecreatePm
                                  : role === 'skill_assistant'
                                  ? handleRecreateSkillAssistant
                                  : handleRecreateCharacterAssistant
                              }
                              className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
                            >
                              <RefreshCw className="w-4 h-4" />
                              {role === 'pm'
                                ? 'Recreate PM Session'
                                : role === 'skill_assistant'
                                ? 'Recreate Skill Assistant'
                                : 'Recreate Character Assistant'}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Close Button */}
                  {onClose && (
                    <button
                      onClick={onClose}
                      className={cn(
                        "p-1.5 rounded transition-colors",
                        role === 'pm'
                          ? "hover:bg-primary-600 text-white"
                          : "hover:bg-primary-200 text-primary-700"
                      )}
                      aria-label="Close"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Error display - exclude "Connection lost" since it's shown in header indicator */}
          {((streamError && streamError !== 'Connection lost') || messagesError) && (
            <div className="p-3 bg-red-50 border-b border-red-200 flex items-center gap-2 w-full max-w-full flex-shrink-0">
              <AlertCircle className="w-4 h-4 text-red-600" />
              <span className="text-sm text-red-700">{messagesError || streamError}</span>
            </div>
          )}

          {/* Read-only indicator */}
          {readOnly && (
            <div className="p-3 bg-yellow-50 border-b border-yellow-200 flex items-center gap-2 w-full max-w-full flex-shrink-0">
              <AlertCircle className="w-4 h-4 text-yellow-600" />
              <span className="text-sm text-yellow-700">This session is read-only</span>
            </div>
          )}

          {/* Messages Area */}
          <div className="flex-1 relative overflow-hidden">
            <div
              ref={messagesContainerRef}
              onScroll={handleScroll}
              className="h-full overflow-y-auto overflow-x-hidden bg-white"
            >
            {(messagesLoading || charactersLoading) ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                  <p className="text-gray-500">
                    {charactersLoading && messagesLoading
                      ? 'Loading...'
                      : charactersLoading
                      ? 'Loading characters...'
                      : 'Loading messages...'}
                  </p>
                </div>
              </div>
            ) : filteredMessages.length === 0 && !streamingState.message ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-5">
                <RoleIcon className="w-8 h-8 mb-2.5 opacity-40 text-gray-400" />
                <p className="text-gray-400 text-sm">
                  {isProcessing ? 'Waiting for output...' : 'No messages yet'}
                </p>
              </div>
            ) : (
              <div className="py-4 w-full max-w-full">
                {(() => {
                  // Group messages by response_id only
                  // Messages with same response_id are part of the same logical response
                  const groupedMessages: Array<{ key: string; messages: typeof filteredMessages }> = [];
                  let currentGroup: typeof filteredMessages = [];
                  let currentResponseId: string | null = null;

                  filteredMessages.forEach((msg, index) => {
                    const msgResponseId = msg.response_id || null;

                    // Start new group if:
                    // 1. No current group
                    // 2. response_id changed
                    // 3. Current message has no response_id (treat as separate)
                    if (
                      currentGroup.length === 0 ||
                      msgResponseId !== currentResponseId ||
                      msgResponseId === null
                    ) {
                      // Save previous group if it exists
                      if (currentGroup.length > 0) {
                        groupedMessages.push({
                          key: currentResponseId || currentGroup[0].id || currentGroup[0].timestamp,
                          messages: currentGroup,
                        });
                      }
                      // Start new group
                      currentGroup = [msg];
                      currentResponseId = msgResponseId;
                    } else {
                      // Add to current group
                      currentGroup.push(msg);
                    }

                    // Handle last message
                    if (index === filteredMessages.length - 1) {
                      groupedMessages.push({
                        key: currentResponseId || currentGroup[0].id || currentGroup[0].timestamp,
                        messages: currentGroup,
                      });
                    }
                  });

                  // Render grouped messages
                  return groupedMessages.map((group) => {
                    // If group has only one message, render normally
                    if (group.messages.length === 1) {
                      const msg = group.messages[0];
                      const toolArgs = msg.role === 'tool_call'
                        ? (Array.isArray(msg.tool_args) ? msg.tool_args?.[0]?.input : msg.tool_args)
                        : undefined;

                      const toolId = msg.role === 'tool_call' && Array.isArray(msg.tool_args)
                        ? msg.tool_args?.[0]?.id
                        : undefined;

                      return (
                        <MessageBubble
                          key={msg.id || msg.timestamp}
                          message={{
                            id: msg.id || msg.timestamp,
                            role: msg.role as 'user' | 'assistant' | 'tool_call' | 'system',
                            content: msg.content,
                            agentName: msg.agent_name,
                            sender_role: msg.sender_role,
                            sender_id: msg.sender_id,
                            sender_name: msg.sender_name,
                            sender_instance: msg.sender_instance,
                            timestamp: new Date(msg.timestamp),
                            isStreaming: false,
                            toolName: msg.tool_name,
                            toolArgs: toolArgs,
                            toolId: toolId,
                          }}
                          agentColor={agentColor}
                          agentAvatar={agentAvatar}
                          characters={characters}
                          onSessionJump={onSessionJump}
                          sessionId={instanceId}
                          userAvatar={userAvatar}
                        />
                      );
                    }

                    // Multiple messages with same response_id - render as unified grouped bubble
                    const groupedMessagesData = group.messages.map((msg) => {
                      const toolArgs = msg.role === 'tool_call'
                        ? (Array.isArray(msg.tool_args) ? msg.tool_args?.[0]?.input : msg.tool_args)
                        : undefined;

                      const toolId = msg.role === 'tool_call' && Array.isArray(msg.tool_args)
                        ? msg.tool_args?.[0]?.id
                        : undefined;

                      return {
                        id: msg.id || msg.timestamp,
                        role: msg.role as 'user' | 'assistant' | 'tool_call' | 'system',
                        content: msg.content,
                        agentName: msg.agent_name,
                        sender_role: msg.sender_role,
                        sender_id: msg.sender_id,
                        sender_name: msg.sender_name,
                        sender_instance: msg.sender_instance,
                        timestamp: new Date(msg.timestamp),
                        isStreaming: false,
                        toolName: msg.tool_name,
                        toolArgs: toolArgs,
                        toolId: toolId,
                      };
                    });

                    return (
                      <MessageGroup
                        key={group.key}
                        messages={groupedMessagesData}
                        agentColor={agentColor}
                        agentAvatar={agentAvatar}
                        characters={characters}
                      />
                    );
                  });
                })()}

                {/* Streaming message */}
                {streamingState.message && (
                  <MessageBubble
                    message={{
                      id: 'streaming',
                      role: 'assistant',
                      content: streamingState.message.content,
                      agentName: streamingState.message.agent_name,
                      timestamp: new Date(streamingState.message.timestamp),
                      isStreaming: true,
                    }}
                    agentColor={agentColor}
                    agentAvatar={agentAvatar}
                    characters={characters}
                    onSessionJump={onSessionJump}
                    sessionId={instanceId}
                    userAvatar={userAvatar}
                  />
                )}

                {/* Typing indicators for specialists */}
                {Array.from(typingAgents).map((agentName) => (
                  <MessageBubble
                    key={`typing-${agentName}`}
                    message={{
                      id: `typing-${agentName}`,
                      role: 'assistant',
                      content: '',
                      agentName,
                      timestamp: new Date(),
                      isStreaming: true,
                    }}
                    agentColor={agentColor}
                    userAvatar={userAvatar}
                    agentAvatar={agentAvatar}
                    characters={characters}
                    isTyping={true}
                    onSessionJump={onSessionJump}
                    sessionId={instanceId}
                  />
                ))}

                <div ref={messagesEndRef} />
              </div>
            )}
            </div>

            {/* Scroll to Bottom Button */}
            {showScrollButton && (
              <button
                onClick={scrollToBottom}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-white hover:bg-gray-50 border border-gray-300 shadow-lg rounded-full p-2 transition-all hover:scale-110 z-10"
                aria-label="Scroll to bottom"
                title="Scroll to latest messages"
              >
                <ArrowDown className="w-5 h-5 text-gray-600" />
              </button>
            )}
          </div>

          {/* Input Area */}
          {!readOnly && (
            <div
              className="pt-2 px-3 lg:px-4 bg-white w-full flex-shrink-0 relative"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {/* Drag-and-drop overlay */}
              {dragOver && (
                <div className="absolute inset-0 bg-blue-500/10 border-2 border-blue-500 border-dashed rounded-lg flex items-center justify-center z-10">
                  <div className="text-center">
                    <Paperclip className="w-12 h-12 mx-auto text-blue-500 mb-2" />
                    <p className="text-blue-600 font-medium">Drop files to attach</p>
                  </div>
                </div>
              )}

              {/* File attachments preview */}
              {hasFiles && (
                <div className="flex flex-wrap gap-2 mb-2 px-4">
                  {attachedFiles.map((file) => (
                    <FileAttachmentPreview
                      key={file.id || file.name}
                      attachedFile={file}
                      onRemove={() => removeFile(file.id || file.name)}
                    />
                  ))}
                </div>
              )}

              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                aria-label="File upload input"
              />

              <div className="flex items-center gap-2 px-4 py-3 border-t-2 border-primary-500 transition-all bg-white">
                {/* Attachment button - always enabled */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600 hover:text-gray-800 transition-colors flex items-center justify-center flex-shrink-0"
                  aria-label="Attach files"
                  title="Attach files"
                >
                  <Paperclip className="w-4 h-4" />
                </button>

                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onCompositionStart={handleCompositionStart}
                  onCompositionEnd={handleCompositionEnd}
                  onPaste={handlePaste}
                  placeholder="Type a message..."
                  rows={1}
                  className="flex-1 bg-transparent text-gray-900 placeholder-gray-400 focus:outline-none disabled:text-gray-500 resize-none max-h-32 overflow-y-auto"
                  aria-label="Chat message input"
                />
                {/* Send button - only disabled if nothing to send */}
                <button
                  onClick={handleSendMessage}
                  disabled={!input.trim() && !hasPreparedFiles}
                  className="relative p-1.5 rounded-md bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0"
                  aria-label="Send message"
                  title={isProcessing ? `Message will be queued${queueSize > 0 ? ` (${queueSize} in queue)` : ''}` : "Send message"}
                >
                  <Send className="w-4 h-4" />
                  {queueSize > 0 && (
                    <span className="absolute -top-1 -right-1 bg-orange-500 text-white text-xs font-semibold rounded-full w-5 h-5 flex items-center justify-center shadow-sm">
                      {queueSize}
                    </span>
                  )}
                </button>
              </div>
            </div>
          )}
      </div>
    </FileContextProvider>
  );
};

// Helper function to get icon component for role
function getRoleIcon(role: SessionRole) {
  switch (role) {
    case 'orchestrator':
      return Target;
    case 'pm':
      return Briefcase;
    case 'skill_assistant':
      return Wrench;
    case 'character_assistant':
      return UserIcon;
  }
}
