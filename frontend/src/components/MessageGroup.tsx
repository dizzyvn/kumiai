/**
 * MessageGroup component
 *
 * Displays multiple messages (text + tools) from the same response_id in a unified bubble.
 */

import { motion } from 'framer-motion';
import { Avatar } from './Avatar';
import type { Message } from '@/types/chat';
import type { AgentCharacter } from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { renderToolWidget } from './ToolWidgets';

// Import markdown components from MessageBubble (we'll need to extract these to shared file later)
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
  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
};

interface MessageGroupProps {
  messages: Message[];
  agentColor: string;
  agentAvatar: string;
  characters: AgentCharacter[];
}

export function MessageGroup({ messages, agentColor, agentAvatar, characters }: MessageGroupProps) {
  if (messages.length === 0) return null;

  // Get display info from first message
  const firstMessage = messages[0];
  let displayAvatar = agentAvatar;
  let displayColor = agentColor;
  let displayName = 'Agent';

  // Look up character for assistant messages
  if (firstMessage.role === 'assistant') {
    // Use sender_name directly if available
    if (firstMessage.sender_name) {
      displayName = firstMessage.sender_name;
    }

    // Look up character for avatar and color (using sender_id as character ID)
    const characterId = firstMessage.agentName || firstMessage.sender_id;
    if (characterId) {
      const character = characters.find(c => c.id === characterId);
      if (character) {
        displayAvatar = character.avatar || character.id || 'default-avatar';
        displayColor = character.color || '#4A90E2';
        // Use character name if we don't have sender_name
        if (!firstMessage.sender_name) {
          displayName = character.name;
        }
      }
    }
  }

  // Use timestamp from first message
  const timestamp = firstMessage.timestamp;

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
          {/* Header with name and timestamp */}
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-semibold text-gray-900 text-base font-sans">{displayName}</span>
            <span className="text-xs text-gray-600">
              {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>

          {/* Render all messages in sequence */}
          <div className="space-y-2">
            {messages.map((msg, index) => {
              if (msg.role === 'assistant' && msg.content) {
                // Text content
                return (
                  <div key={msg.id || index} className="text-[15px] leading-relaxed break-words overflow-x-auto">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                );
              } else if (msg.role === 'tool_call') {
                // Tool use - render using widget system
                return (
                  <div key={msg.id || index}>
                    {renderToolWidget({
                      toolName: msg.toolName || 'Unknown Tool',
                      toolArgs: msg.toolArgs || {},
                      toolId: msg.toolId,
                    })}
                  </div>
                );
              }
              return null;
            })}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

