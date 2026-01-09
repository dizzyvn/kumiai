import { motion } from 'framer-motion';
import { Avatar } from './Avatar';
import type { Message, FileAttachment as StructuredFileAttachment } from '@/types/chat';
import type { AgentCharacter } from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import type { Components } from 'react-markdown';
import { useMemo, memo } from 'react';
import { truncateText } from '@/lib/utils';
import { File } from './File';
import { FileErrorBoundary } from './FileErrorBoundary';
import { useOptionalFileContext } from '@/contexts/FileContext';
import { renderToolWidget } from './ToolWidgets';
import { Settings } from 'lucide-react';

// Parse legacy file attachments from message content (for backward compatibility)
function parseFileAttachments(content: string): { text: string; files: StructuredFileAttachment[] } {
  const fileAttachmentMatch = content.match(/📎 \*\*Attached files:\*\*\n((?:- .+\n?)+)/);

  if (!fileAttachmentMatch) {
    return { text: content, files: [] };
  }

  const [fullMatch, fileList] = fileAttachmentMatch;
  const messageText = content.replace(fullMatch, '').trim();

  const files = fileList
    .split('\n')
    .filter(line => line.startsWith('-'))
    .map(line => {
      // Format: - filename.ext (12.3KB) at working/filename.ext
      const match = line.match(/- (.+?) \((.+?)\) at (.+)/);
      if (!match) return null;

      const [, name, sizeStr, path] = match;
      // Convert size string to bytes (approximate)
      const size = parseSizeString(sizeStr);

      return { name, size, path };
    })
    .filter((f): f is StructuredFileAttachment => f !== null);

  return { text: messageText, files };
}

// Helper to convert size strings like "12.3KB" to bytes
function parseSizeString(sizeStr: string): number {
  const match = sizeStr.match(/^([\d.]+)(B|KB|MB)$/);
  if (!match) return 0;

  const [, numStr, unit] = match;
  const num = parseFloat(numStr);

  switch (unit) {
    case 'B': return num;
    case 'KB': return num * 1024;
    case 'MB': return num * 1024 * 1024;
    default: return 0;
  }
}

// File attachments display component
function FileAttachmentsDisplay({ files }: { files: StructuredFileAttachment[] }) {
  const fileContext = useOptionalFileContext();

  if (!fileContext?.isReady) {
    return (
      <div className="mt-2 text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">
        ⚠️ Cannot display {files.length} file{files.length > 1 ? 's' : ''}: File context not available
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {files.map((file, i) => (
        <FileErrorBoundary key={`${file.path}-${i}`}>
          <File attachment={file} mode="compact" />
        </FileErrorBoundary>
      ))}
    </div>
  );
}

// Tool call bubble component (for role='tool_call' messages)
function ToolCallBubble({ message }: { message: Message }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="px-5 py-3"
    >
      {renderToolWidget({
        toolName: message.toolName || 'Unknown Tool',
        toolArgs: message.toolArgs || {},
        toolId: message.toolId,
      })}
    </motion.div>
  );
}


// Simple content renderer without tool marker processing
function MessageContent({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  );
}

// Custom markdown components
const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-2.5 leading-normal text-gray-900">{children}</p>,
  ul: ({ children }) => <ul className="list-none ml-5 mb-2.5 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-none ml-5 mb-2.5 space-y-1 counter-reset-[item]">{children}</ol>,
  li: ({ children }) => (
    <li className="leading-normal before:content-['–'] before:absolute before:-ml-4 before:text-gray-600 relative">
      {children}
    </li>
  ),
  h1: ({ children }) => <h1 className="text-3xl font-semibold mt-6 mb-2.5 text-gray-900 tracking-tight">{children}</h1>,
  h2: ({ children }) => <h2 className="text-2xl font-semibold mt-5 mb-2 text-gray-900">{children}</h2>,
  h3: ({ children }) => <h3 className="text-xl font-semibold mt-4 mb-2 text-gray-900">{children}</h3>,
  h4: ({ children }) => <h4 className="text-lg font-medium mt-3 mb-1 text-gray-600">{children}</h4>,
  h5: ({ children }) => <h5 className="text-base font-medium mt-2 mb-1 text-gray-600">{children}</h5>,
  h6: ({ children }) => <h6 className="text-sm font-medium mt-2 mb-1 text-gray-600 uppercase tracking-wide">{children}</h6>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-primary-300 pl-4 pr-3 pt-2 pb-1 my-3 bg-primary-50/30 text-gray-900 italic leading-normal rounded-r">
      {children}
    </blockquote>
  ),
  code: ({ inline, className, children, ...props }) => {
    const isInline = inline ?? !className?.includes('language-');

    if (isInline) {
      return (
        <code className="inline-block bg-primary-50 text-primary-800 mx-1 px-1 py-0.5 font-mono text-[90%] rounded-sm border border-primary-200">
          {children}
        </code>
      );
    }
    return (
      <code className="block bg-primary-50 text-primary-800 px-3 py-2 my-3 text-sm font-mono overflow-x-auto leading-normal border border-primary-200 rounded">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-3">{children}</pre>,
  a: ({ href, children }) => (
    <a href={href} className="text-primary-700 underline decoration-1 underline-offset-2 hover:text-primary-800 transition-colors" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  hr: () => <hr className="my-6 border-t border-primary-200" />,
  table: ({ children }) => (
    <div className="overflow-x-auto my-5">
      <table className="w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-b border-primary-200">{children}</tr>,
  th: ({ children }) => <th className="px-3 py-2 text-left font-normal text-gray-900 border-b-2 border-gray-900">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 text-gray-900">{children}</td>,
  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  del: ({ children }) => <del className="line-through text-gray-600">{children}</del>,
  br: () => <br />,
};

interface MessageBubbleProps {
  message: Message;
  agentColor: string;
  agentAvatar: string;
  characters: AgentCharacter[];
  isTyping?: boolean;
  onSessionJump?: (sessionId: string) => void;
  sessionId?: string; // Session ID for file operations
  userAvatar?: string; // User profile avatar (base64 or URL)
}

export const MessageBubble = memo(function MessageBubble({ message, agentColor, agentAvatar, characters, isTyping = false, onSessionJump, sessionId, userAvatar }: MessageBubbleProps) {
  // Look up character for assistant messages (using agentName OR sender_name)
  let displayAvatar = agentAvatar;
  let displayColor = agentColor;
  let displayName = 'Agent';

  if (message.role === 'assistant') {
    // Use sender_name directly if available, otherwise look up character
    if (message.sender_name) {
      displayName = message.sender_name;
    }

    // Look up character for avatar and color (using sender_id as character ID)
    const characterId = message.agentName || message.sender_id;
    if (characterId) {
      const character = characters.find(c => c.id === characterId);
      if (character) {
        displayAvatar = character.avatar || character.id || 'default-avatar';
        displayColor = character.color || '#4A90E2';
        // Use character name if we don't have sender_name
        if (!message.sender_name) {
          displayName = character.name;
        }
      }
    }
  }

  if (message.role === 'user') {
    // Look up sender character if sender_name is set (same pattern as agentName for assistants)
    let senderAvatar = 'default-avatar';
    let senderColor = '#6B7280';
    let senderName = 'You';
    let useAvatar = false;

    if (message.sender_role === 'pm' && message.sender_name) {
      // Find PM character by ID (sender_name contains character ID)
      const pmCharacter = characters.find(c =>
        c.id === message.sender_name || c.name === message.sender_name
      );
      if (pmCharacter) {
        senderAvatar = pmCharacter.avatar || pmCharacter.id || 'default-avatar';
        senderColor = pmCharacter.color || '#3B82F6';
        senderName = pmCharacter.name;
        useAvatar = true;
      } else {
        // Character not found - show descriptive fallback
        if (message.sender_id) {
          senderName = `PM (${message.sender_id})`;
        } else {
          senderName = message.sender_name;
        }
      }
    } else if ((message.sender_role === 'orchestrator' || message.sender_role === 'specialist' || message.sender_role === 'single_specialist') && message.sender_name) {
      // Find orchestrator/specialist character by ID (sender_name contains character ID)
      const senderCharacter = characters.find(c =>
        c.id === message.sender_name || c.name === message.sender_name
      );
      if (senderCharacter) {
        senderAvatar = senderCharacter.avatar || senderCharacter.id || 'default-avatar';
        senderColor = senderCharacter.color || (message.sender_role === 'orchestrator' ? '#9333EA' : '#4A90E2');
        senderName = senderCharacter.name;
        useAvatar = true;
      } else {
        // Character not found - show descriptive fallback
        const roleLabel = message.sender_role === 'orchestrator' ? 'Orchestrator' :
                         message.sender_role === 'single_specialist' ? 'Specialist' : 'Specialist';
        if (message.sender_id) {
          senderName = `${roleLabel} (${message.sender_id})`;
        } else {
          senderName = message.sender_name;
        }
        senderAvatar = message.sender_name;
        senderColor = message.sender_role === 'orchestrator' ? '#9333EA' : '#4A90E2';
        useAvatar = true;
      }
    } else if (message.sender_role === 'system' && message.sender_name) {
      // System messages (reminders, notifications, etc.)
      senderName = message.sender_name; // e.g., "Reminder"
      senderColor = '#F59E0B'; // Amber color for system messages
      // Don't set useAvatar - we'll render a special icon below
    }

    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="group px-5 py-3"
      >
        <div className="flex gap-2.5 w-full max-w-full">
          {message.sender_role === 'system' ? (
            <div className="w-10 h-10 mt-1 rounded-lg bg-amber-100 flex items-center justify-center text-amber-600 flex-shrink-0">
              <Settings className="w-6 h-6" />
            </div>
          ) : useAvatar ? (
            <Avatar
              seed={senderAvatar}
              size={40}
              className="w-10 h-10 flex-shrink-0 rounded"
              color={senderColor}
            />
          ) : userAvatar ? (
            <div className="w-10 h-10 mt-1 rounded-lg overflow-hidden flex items-center justify-center bg-primary-50 flex-shrink-0">
              <img
                src={userAvatar}
                alt="User"
                className="w-full h-full object-cover"
              />
            </div>
          ) : (
            <div className="w-10 h-10 mt-1 rounded-lg bg-primary-600 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
              👤
            </div>
          )}
          <div className="flex-1 min-w-0 max-w-full">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="font-semibold text-gray-900 text-base font-sans">{senderName}</span>
              <span className="text-xs text-gray-600">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            {/* Show sender session for cross-session messages */}
            {message.sender_id && (
              <div className="text-xs text-gray-500 mb-1.5 italic">
                <span className="font-medium">From:</span>{' '}
                <span className="font-mono">{message.sender_id}</span>
              </div>
            )}
            <div className="text-[15px] leading-relaxed break-words overflow-x-auto">
              {(() => {
                const { text, files } = parseFileAttachments(message.content);
                // Combine structured attachments with legacy parsed attachments
                const allFiles = [...(message.attachments || []), ...files];

                return (
                  <>
                    {text && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {text}
                      </ReactMarkdown>
                    )}
                    {allFiles.length > 0 && <FileAttachmentsDisplay files={allFiles} />}
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === 'assistant') {
    // Use sender_name if available (new schema), otherwise fall back to displayName
    const assistantName = message.sender_name || displayName;

    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="group px-5 py-3"
      >
        <div className="flex gap-2.5 w-full max-w-full">
          <Avatar
            seed={displayAvatar}
            size={40}
            className="w-10 h-10 flex-shrink-0 rounded"
            color={displayColor}
          />
          <div className="flex-1 min-w-0 max-w-full">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="font-semibold text-gray-900 text-base font-sans">{assistantName}</span>
              <span className="text-xs text-gray-600">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>

            {/* Message content or typing indicator */}
            {isTyping ? (
              <div className="flex gap-1">
                <motion.div
                  className="w-2 h-2 rounded-full bg-gray-400"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ repeat: Infinity, duration: 1.2, delay: 0 }}
                />
                <motion.div
                  className="w-2 h-2 rounded-full bg-gray-400"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ repeat: Infinity, duration: 1.2, delay: 0.2 }}
                />
                <motion.div
                  className="w-2 h-2 rounded-full bg-gray-400"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ repeat: Infinity, duration: 1.2, delay: 0.4 }}
                />
              </div>
            ) : message.content && (
              <div className="text-[15px] leading-relaxed break-words overflow-x-auto">
                {(() => {
                  const { text, files } = parseFileAttachments(message.content);
                  // Combine structured attachments with legacy parsed attachments
                  const allFiles = [...(message.attachments || []), ...files];

                  return (
                    <>
                      <MessageContent content={text} />
                      {allFiles.length > 0 && <FileAttachmentsDisplay files={allFiles} />}
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === 'tool_call') {
    return <ToolCallBubble message={message} />;
  }

  if (message.role === 'system') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="px-5 py-3"
      >
        <div className="flex items-center justify-center">
          <div className="px-4 py-1.5 bg-yellow-50 border border-yellow-200 rounded-full">
            <p className="text-xs text-yellow-800 text-center whitespace-pre-wrap">
              {message.content}
            </p>
          </div>
        </div>
      </motion.div>
    );
  }

  return null;
}, (prevProps, nextProps) => {
  // Custom comparison: only re-render if message content, id, or typing status changes
  return (
    prevProps.message.id === nextProps.message.id &&
    prevProps.message.content === nextProps.message.content &&
    prevProps.message.role === nextProps.message.role &&
    prevProps.isTyping === nextProps.isTyping &&
    prevProps.agentColor === nextProps.agentColor &&
    prevProps.agentAvatar === nextProps.agentAvatar &&
    prevProps.userAvatar === nextProps.userAvatar
    // Deliberately ignore characters array - doesn't affect individual message rendering
  );
});
