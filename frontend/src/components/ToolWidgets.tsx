/**
 * Tool Widgets for rendering tool use messages
 *
 * Each tool type has a dedicated widget component that handles:
 * - Tool invocation display (parameters)
 * - Loading state
 * - Result display
 *
 * Inspired by opcode's widget-based rendering pattern
 */

import React, { useState, Suspense, lazy } from 'react';
import {
  Terminal,
  FileText,
  Edit3,
  FilePlus,
  MessageSquare,
  Users,
  PlayCircle,
  Wrench,
  ListChecks,
  CheckCircle2,
  Clock,
  Circle,
  Bell,
  LayoutDashboard,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Upload,
  Image,
  FileCode,
  File as FileIcon,
  Eye,
  Loader2,
  Download
} from 'lucide-react';
import { truncateMcpPrefix } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { detectFileType } from '@/lib/fileTypeDetector';
import { useOptionalFileContext } from '@/contexts/FileContext';

const FileViewerModal = lazy(() => import('./FileViewerModal').then(m => ({ default: m.FileViewerModal })));

// ============================================================================
// Types
// ============================================================================

export interface ToolWidgetProps {
  toolName: string;
  toolArgs: Record<string, unknown>;
  toolId?: string;
  result?: any;
  isLoading?: boolean;
}

// ============================================================================
// Shared Styles
// ============================================================================

const WIDGET_HEADER_TEXT_SIZE = "text-sm"; // Shared header text size

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Collapsible Widget Wrapper
 */
interface CollapsibleWidgetProps {
  header: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  collapsible?: boolean; // If false, always shows content without chevron
}

const CollapsibleWidget: React.FC<CollapsibleWidgetProps> = ({
  header,
  children,
  defaultExpanded = false,
  collapsible = true
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!collapsible) {
    // Non-collapsible: always show content, no chevron, no hover effect
    return (
      <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
        <div className="px-4 py-2 bg-gray-50 flex items-center gap-2 border-b border-gray-200 min-w-0">
          {header}
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div
        className="px-4 py-2 bg-gray-50 flex items-center gap-2 border-b border-gray-200 min-w-0 cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {header}
        {isExpanded ? (
          <ChevronUp className="h-3.5 w-3.5 text-gray-500 ml-auto flex-shrink-0" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-gray-500 ml-auto flex-shrink-0" />
        )}
      </div>
      {isExpanded && children}
    </div>
  );
};

/**
 * Parse tool result content from various formats
 */
function parseResultContent(result: any): { content: string; isError: boolean } {
  if (!result) {
    return { content: '', isError: false };
  }

  let content = '';
  const isError = result.is_error || false;

  if (typeof result.content === 'string') {
    content = result.content;
  } else if (result.content && typeof result.content === 'object') {
    if (result.content.text) {
      content = result.content.text;
    } else if (Array.isArray(result.content)) {
      content = result.content
        .map((c: any) => (typeof c === 'string' ? c : c.text || JSON.stringify(c)))
        .join('\n');
    } else {
      content = JSON.stringify(result.content, null, 2);
    }
  }

  return { content, isError };
}

// ============================================================================
// Show File Widget
// ============================================================================

/**
 * ShowFile Widget - displays file with thumbnail and click-to-view modal
 */
export const ShowFileWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const filePath = (toolArgs.file_path || toolArgs.path) as string | undefined;
  const fileContext = useOptionalFileContext();
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Handle missing file path
  if (!filePath) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <div className="flex items-center gap-2 text-sm text-red-800">
          <Eye className="h-4 w-4 flex-shrink-0" />
          <span>Error: No file path provided</span>
        </div>
      </div>
    );
  }

  const fileInfo = detectFileType(filePath);
  const fileName = filePath.split('/').pop() || filePath;
  const isImage = fileInfo.type === 'image';
  const { content: resultContent, isError } = parseResultContent(result);

  // Get file URL if context is available
  const fileUrl = fileContext?.isReady ? fileContext.getFileUrl(filePath) : null;

  // Handle download
  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent opening viewer when clicking download
    setDownloadError(null);
    if (!fileContext?.isReady) return;

    try {
      const blob = await fileContext.downloadFile(filePath);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to download file:', err);
      setDownloadError(err instanceof Error ? err.message : 'Download failed');
    }
  };

  // Format file size
  const formatSize = (path: string): string => {
    // We don't have actual size, so just show file type info
    if (fileInfo.language) return fileInfo.language;
    return fileInfo.type;
  };

  // Get file icon based on type
  const getFileIcon = () => {
    const iconClass = "w-5 h-5 text-gray-400";

    switch (fileInfo.type) {
      case 'image':
        return <Image className={iconClass} />;
      case 'code':
        return <FileCode className={iconClass} />;
      case 'markdown':
      case 'text':
        return <FileText className={iconClass} />;
      default:
        return <FileIcon className={iconClass} />;
    }
  };

  const header = (
    <>
      <Eye className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Show:</span>
      <code className={`${WIDGET_HEADER_TEXT_SIZE} font-mono text-gray-600 truncate`} title={filePath}>{filePath}</code>
    </>
  );

  return (
    <CollapsibleWidget header={header} defaultExpanded={true}>
      <div className="p-4">
        {/* File card - horizontal layout matching sent attachment card */}
        <div
          className="inline-flex items-center gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition-colors max-w-md group cursor-pointer"
          onClick={() => {
            if (fileContext?.isReady) {
              setIsViewerOpen(true);
            }
          }}
          title={fileContext?.isReady ? `Click to view ${fileName}` : 'File context not available'}
        >
          {/* Thumbnail */}
          <div className="w-16 h-16 flex-shrink-0">
            {isImage && fileUrl && !imageError ? (
              <img
                src={fileUrl}
                alt={fileName}
                className="w-full h-full object-cover rounded"
                onError={() => setImageError(true)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-gray-100 rounded">
                {getFileIcon()}
              </div>
            )}
          </div>

          {/* File Info */}
          <div className="flex-1 min-w-0">
            <div className="font-medium text-sm text-gray-900 truncate" title={fileName}>
              {fileName}
            </div>
            <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-2">
              <span>{formatSize(filePath)}</span>
            </div>
          </div>

          {/* Actions */}
          {fileContext?.isReady && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={handleDownload}
                className="p-1.5 text-gray-600 hover:bg-gray-200 rounded transition-colors"
                title="Download file"
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* Warning if no file context */}
        {!fileContext?.isReady && (
          <div className="mt-2 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">
            ⚠️ Cannot preview file: File context not available
          </div>
        )}

        {/* Download error */}
        {downloadError && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">
            {downloadError}
          </div>
        )}

        {/* Result */}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}

        {/* File viewer modal */}
        {isViewerOpen && fileContext?.isReady && (
          <Suspense fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <Loader2 className="w-8 h-8 text-white animate-spin" />
            </div>
          }>
            <FileViewerModal
              mode={fileContext.contextType}
              projectId={fileContext.contextType === 'project' ? fileContext.contextId : undefined}
              sessionId={fileContext.contextType === 'session' ? fileContext.contextId : undefined}
              filePath={filePath}
              onClose={() => setIsViewerOpen(false)}
            />
          </Suspense>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Default Tool Widget (Fallback for unknown tools)
// ============================================================================

export const DefaultToolWidget: React.FC<ToolWidgetProps> = ({
  toolName,
  toolArgs,
  result
}) => {
  const { content: resultContent, isError } = parseResultContent(result);

  const header = (
    <>
      <Wrench className="w-3.5 h-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={toolName}>
        {truncateMcpPrefix(toolName)}
      </span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-3">
        {/* Tool arguments */}
        {Object.keys(toolArgs).length > 0 && (
          <div className="p-2 bg-gray-50 rounded border border-gray-200">
            <pre className="text-xs font-mono overflow-x-auto text-gray-800">
              {JSON.stringify(toolArgs, null, 2)}
            </pre>
          </div>
        )}

        {/* Tool result */}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-800'
              : 'bg-green-50 border-green-200 text-green-800'
          }`}>
            <pre className="font-mono overflow-x-auto whitespace-pre-wrap">
              {resultContent}
            </pre>
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Bash Tool Widget
// ============================================================================

export const BashWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const command = toolArgs.command as string;
  const description = toolArgs.description as string | undefined;
  const { content: resultContent, isError } = parseResultContent(result);

  const header = (
    <>
      <Terminal className="h-3.5 w-3.5 flex-shrink-0 text-green-600" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Exec:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={description || command}>
        {description || command}
      </span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-3">
        <code className="text-xs font-mono block text-green-600">
          $ {command}
        </code>

        {/* Result */}
        {result && (
          <div className={`p-3 rounded border text-xs font-mono whitespace-pre-wrap overflow-x-auto ${
            isError
              ? 'border-red-200 bg-red-50 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent || (isError ? 'Command failed' : 'Command completed')}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Read Tool Widget
// ============================================================================

export const ReadWidget: React.FC<ToolWidgetProps> = ({
  toolArgs
}) => {
  const filePath = toolArgs.file_path as string;

  const header = (
    <>
      <FileText className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Read:</span>
      <code className={`${WIDGET_HEADER_TEXT_SIZE} font-mono text-gray-600 truncate`} title={filePath}>{filePath}</code>
    </>
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 flex items-center gap-2 min-w-0">
        {header}
      </div>
    </div>
  );
};

// ============================================================================
// Write Tool Widget
// ============================================================================

export const WriteWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const filePath = toolArgs.file_path as string;
  const content = toolArgs.content as string;
  const { content: resultContent, isError } = parseResultContent(result);

  const previewContent = content && content.length > 200
    ? content.substring(0, 200) + '\n...'
    : content || '';

  const header = (
    <>
      <FilePlus className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Write:</span>
      <code className={`${WIDGET_HEADER_TEXT_SIZE} font-mono text-gray-800 truncate`} title={filePath}>{filePath}</code>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        <div className="text-xs text-gray-500 uppercase tracking-wide">Preview</div>
        <div className="p-2 bg-gray-50 rounded border border-gray-200">
          <pre className="text-xs font-mono overflow-x-auto text-gray-700">
            {previewContent}
          </pre>
        </div>

        {/* Result */}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Edit Tool Widget
// ============================================================================

export const EditWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const filePath = toolArgs.file_path as string;
  const oldString = toolArgs.old_string as string;
  const newString = toolArgs.new_string as string;
  const { content: resultContent, isError } = parseResultContent(result);

  const header = (
    <>
      <Edit3 className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Edit:</span>
      <code className={`${WIDGET_HEADER_TEXT_SIZE} font-mono text-gray-800 truncate`} title={filePath}>{filePath}</code>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-3">
        {/* Old and New content side by side */}
        <div className="grid grid-cols-2 gap-3">
          {/* Old content */}
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Old</div>
            <div className="p-2 bg-red-50 border border-red-200 rounded">
              <pre className="text-xs font-mono overflow-x-auto text-red-700">
                {oldString}
              </pre>
            </div>
          </div>

          {/* New content */}
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">New</div>
            <div className="p-2 bg-green-50 border border-green-200 rounded">
              <pre className="text-xs font-mono overflow-x-auto text-green-700">
                {newString}
              </pre>
            </div>
          </div>
        </div>

        {/* Result */}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// App-Specific Widgets
// ============================================================================

/**
 * Contact PM Widget - for orchestrators to send messages to PM
 */
export const ContactPMWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const message = toolArgs.message as string;
  const { content: resultContent, isError } = parseResultContent(result);

  // Truncate message for header
  const truncatedMessage = message.length > 50 ? message.substring(0, 50) + '...' : message;

  const header = (
    <>
      <MessageSquare className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Message to PM:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={message}>{truncatedMessage}</span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        <div className="text-sm text-gray-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message}</ReactMarkdown>
        </div>
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

/**
 * Contact Session Widget - for PM to send messages to sessions
 */
export const ContactSessionWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const instanceId = toolArgs.instance_id as string;
  const message = toolArgs.message as string;
  const { content: resultContent, isError } = parseResultContent(result);

  // Truncate session ID for header
  const truncatedId = instanceId.length > 16 ? instanceId.substring(0, 16) + '...' : instanceId;

  const header = (
    <>
      <Users className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Message to:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={instanceId}>{truncatedId}</span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Session ID</div>
          <code className="text-xs font-mono text-primary-600 bg-primary-100 px-2 py-1 rounded block">
            {instanceId}
          </code>
        </div>
        <div className="text-sm text-gray-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message}</ReactMarkdown>
        </div>
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

/**
 * Spawn Session Widget - for PM to create new sessions
 */
export const SpawnSessionWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const sessionDescription = toolArgs.session_description as string;
  const selectedSpecialists = toolArgs.selected_specialists as string[] | undefined;
  const { content: resultContent, isError } = parseResultContent(result);

  // Truncate description for header
  const truncatedDesc = sessionDescription.length > 40 ? sessionDescription.substring(0, 40) + '...' : sessionDescription;

  const header = (
    <>
      <PlayCircle className="h-3.5 w-3.5 flex-shrink-0 text-accent" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Spawn:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={sessionDescription}>{truncatedDesc}</span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Description</div>
          <div className="text-sm text-gray-700">{sessionDescription}</div>
        </div>
        {selectedSpecialists && selectedSpecialists.length > 0 && (
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Specialists</div>
            <div className="flex flex-wrap gap-1">
              {selectedSpecialists.map((specialist, idx) => (
                <span
                  key={idx}
                  className="text-xs px-2 py-0.5 rounded border bg-accent-50 text-accent-700 border-accent-200"
                >
                  {specialist}
                </span>
              ))}
            </div>
          </div>
        )}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            <pre className="font-mono whitespace-pre-wrap overflow-x-auto">
              {resultContent}
            </pre>
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// TodoWrite Widget
// ============================================================================

/**
 * TodoWrite Widget - displays todo list with status indicators
 */
export const TodoWriteWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const todos = toolArgs.todos as any[] | undefined;
  const { content: resultContent, isError } = parseResultContent(result);

  const statusIcons = {
    completed: <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />,
    in_progress: <Clock className="h-3.5 w-3.5 animate-pulse text-primary-600" />,
    pending: <Circle className="h-3.5 w-3.5 text-gray-400" />
  };

  const todoCount = todos?.length || 0;
  const completedCount = todos?.filter(t => t.status === 'completed').length || 0;

  const header = (
    <>
      <ListChecks className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Tasks:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>
        {todoCount > 0 ? `${completedCount}/${todoCount} completed` : 'No tasks'}
      </span>
    </>
  );

  if (!todos || todos.length === 0) {
    return (
      <CollapsibleWidget header={header}>
        <div className="p-4 text-xs text-gray-500">No todos</div>
      </CollapsibleWidget>
    );
  }

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        {todos.map((todo, idx) => (
          <div
            key={idx}
            className={`flex items-start gap-2 p-2 rounded border ${
              todo.status === 'completed' ? 'bg-gray-50 opacity-60' : 'bg-white'
            }`}
          >
            <div className="mt-0.5 flex-shrink-0">
              {statusIcons[todo.status as keyof typeof statusIcons] || statusIcons.pending}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs ${todo.status === 'completed' ? 'line-through text-gray-500' : 'text-gray-900'}`}>
                {todo.content}
              </p>
              {todo.activeForm && todo.status === 'in_progress' && (
                <p className="text-xs text-blue-600 mt-0.5">{todo.activeForm}</p>
              )}
            </div>
          </div>
        ))}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs mt-2 ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Remind Widget
// ============================================================================

/**
 * Remind Widget - displays scheduled reminder information
 */
export const RemindWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const delaySeconds = toolArgs.delay_seconds as number;
  const message = toolArgs.message as string;
  const { content: resultContent, isError } = parseResultContent(result);

  // Format delay time
  const formatDelay = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const header = (
    <>
      <Bell className="h-3.5 w-3.5 flex-shrink-0 text-yellow-500" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Remind in:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>{formatDelay(delaySeconds)}</span>
    </>
  );

  return (
    <CollapsibleWidget header={header}>
      <div className="p-4 space-y-2">
        <div className="text-sm text-gray-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message}</ReactMarkdown>
        </div>
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Get Project Status Widget
// ============================================================================

/**
 * GetProjectStatus Widget - displays project overview with sessions grouped by stage
 */
export const GetProjectStatusWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const projectId = toolArgs.project_id as string;
  const { content: resultContent, isError } = parseResultContent(result);

  // Parse result text to extract session data
  const parseProjectStatus = (text: string) => {
    const lines = text.split('\n');
    const stages: Record<string, Array<{ id: string; description: string; execution: string; status: string; role: string }>> = {
      BACKLOG: [],
      ACTIVE: [],
      WAITING: [],
      DONE: []
    };

    let currentStage = '';
    let currentSession: any = {};

    for (const line of lines) {
      // Check for stage headers
      const stageMatch = line.match(/^(BACKLOG|ACTIVE|WAITING|DONE) \((\d+)\):/);
      if (stageMatch) {
        currentStage = stageMatch[1];
        continue;
      }

      // Parse session ID
      if (line.trim().startsWith('• ID:')) {
        if (currentSession.id) {
          stages[currentStage]?.push(currentSession);
        }
        currentSession = { id: line.replace(/.*ID:\s*/, '').trim() };
      }
      // Parse description
      else if (line.trim().startsWith('Description:')) {
        currentSession.description = line.replace(/.*Description:\s*/, '').trim();
      }
      // Parse execution and status
      else if (line.trim().startsWith('Execution:')) {
        const parts = line.split('|');
        currentSession.execution = parts[0]?.replace(/.*Execution:\s*/, '').trim() || '';
        currentSession.status = parts[1]?.replace(/.*Kanban Status:\s*/, '').trim() || '';
        currentSession.role = parts[2]?.replace(/.*Role:\s*/, '').trim() || '';
      }
    }

    // Add last session
    if (currentSession.id && currentStage) {
      stages[currentStage]?.push(currentSession);
    }

    return stages;
  };

  const stages = result && resultContent ? parseProjectStatus(resultContent) : null;

  // Stage colors from design system
  const stageStyles = {
    BACKLOG: { bg: '#f9f9f9', border: '#e5e5e6', text: '#99999b' },  // Gray scale
    ACTIVE: { bg: '#fcecee', border: '#f3b3b9', text: '#e03a46' },   // Red
    WAITING: { bg: '#eff2fb', border: '#bfcbef', text: '#253779' },  // Blue
    DONE: { bg: '#f2fbed', border: '#cbefb7', text: '#65b52a' }      // Green
  };

  const header = (
    <>
      <LayoutDashboard className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Status:</span>
      <code className={`${WIDGET_HEADER_TEXT_SIZE} font-mono text-gray-600 truncate`} title={projectId}>{projectId}</code>
    </>
  );

  return (
    <CollapsibleWidget header={header} collapsible={false}>
      {result && !isError && stages && (
        <div className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.entries(stageStyles).map(([stage, style]) => {
              const sessions = stages[stage] || [];
              return (
                <div key={stage} className="flex flex-col">
                  <div
                    className="text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded-t border-b-2"
                    style={{ backgroundColor: style.bg, borderColor: style.border, color: style.text }}
                  >
                    {stage} ({sessions.length})
                  </div>
                  <div className="border border-t-0 border-gray-200 rounded-b p-2 space-y-2 min-h-[100px]">
                    {sessions.map((session, idx) => (
                      <div key={idx} className="p-2 bg-gray-50 rounded border border-gray-200 text-xs">
                        <div className="font-mono text-gray-600 truncate mb-1" title={session.id}>
                          {session.id.substring(0, 12)}...
                        </div>
                        <div className="text-gray-700 line-clamp-2 mb-1">
                          {session.description}
                        </div>
                        <div className="text-[10px] text-gray-500">
                          {session.execution}
                        </div>
                      </div>
                    ))}
                    {sessions.length === 0 && (
                      <div className="text-center text-xs text-gray-400 py-4">
                        No sessions
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {result && isError && (
        <div className="p-4">
          <div className="p-2 rounded border text-xs bg-red-50 border-red-200 text-red-700">
            {resultContent}
          </div>
        </div>
      )}
    </CollapsibleWidget>
  );
};

// ============================================================================
// Update Instance Stage Widget
// ============================================================================

/**
 * UpdateInstanceStage Widget - displays session stage transition
 */
export const UpdateInstanceStageWidget: React.FC<ToolWidgetProps> = ({
  toolArgs
}) => {
  const instanceId = toolArgs.instance_id as string;
  const newStage = toolArgs.new_stage as string;

  // Stage display info
  const stageInfo: Record<string, { label: string }> = {
    waiting: { label: 'Waiting' },
    done: { label: 'Done' }
  };

  const stage = stageInfo[newStage] || stageInfo.waiting;

  // Truncate session ID for header
  const truncatedId = instanceId.length > 16 ? instanceId.substring(0, 16) + '...' : instanceId;

  const header = (
    <>
      <ArrowRight className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Move to {stage.label}:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`} title={instanceId}>{truncatedId}</span>
    </>
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 flex items-center gap-2 min-w-0">
        {header}
      </div>
    </div>
  );
};

// ============================================================================
// File Upload Widget
// ============================================================================

/**
 * FileUpload Widget - displays file upload tool with thumbnail preview and click-to-open
 */
export const FileUploadWidget: React.FC<ToolWidgetProps> = ({
  toolArgs,
  result
}) => {
  const filePath = (toolArgs.filePath || (toolArgs.paths as string[] | undefined)?.[0]) as string | undefined;
  const paths = toolArgs.paths as string[] | undefined;
  const { content: resultContent, isError } = parseResultContent(result);

  // Get file icon based on file type
  const getFileIcon = (path: string) => {
    const fileInfo = detectFileType(path);
    const iconClass = "w-8 h-8";

    switch (fileInfo.type) {
      case 'image':
        return <Image className={iconClass} />;
      case 'code':
        return <FileCode className={iconClass} />;
      case 'text':
      case 'markdown':
        return <FileText className={iconClass} />;
      default:
        return <FileIcon className={iconClass} />;
    }
  };

  // Get file name from path
  const getFileName = (path: string) => {
    return path.split('/').pop() || path;
  };

  // Open file in default application (simplified - actual implementation would need backend support)
  const openFile = (path: string) => {
    // In a real implementation, this would call a Tauri command or backend API
    // to open the file with the system's default application
    console.log('Opening file:', path);

    // For now, just show an alert
    alert(`Opening file: ${path}\n\nIn a production environment, this would open the file with your system's default application.`);
  };

  // Generate thumbnail for image files
  const FileThumbnail: React.FC<{ path: string }> = ({ path }) => {
    const fileInfo = detectFileType(path);
    const isImage = fileInfo.type === 'image';
    const fileName = getFileName(path);

    return (
      <div
        className="relative group cursor-pointer"
        onClick={() => openFile(path)}
        title={`Click to open ${fileName}`}
      >
        <div className="w-20 h-20 rounded-lg border-2 border-gray-200 bg-gray-50 p-2 flex items-center justify-center overflow-hidden hover:border-primary-400 hover:bg-primary-50 transition-all">
          {isImage ? (
            <div className="relative w-full h-full">
              {/* For actual image preview, we'd need to load the file */}
              <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-blue-100 to-purple-100 rounded">
                <Image className="w-8 h-8 text-primary-600" />
              </div>
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 transition-colors rounded" />
            </div>
          ) : (
            <div className="text-gray-500 group-hover:text-primary-600 transition-colors">
              {getFileIcon(path)}
            </div>
          )}
        </div>
        <div className="mt-1 text-xs text-center">
          <p className="truncate max-w-[88px] font-medium text-gray-700 group-hover:text-primary-700" title={fileName}>
            {fileName}
          </p>
        </div>
      </div>
    );
  };

  const uploadedFiles = paths || (filePath ? [filePath] : []);
  const fileCount = uploadedFiles.length;

  const header = (
    <>
      <Upload className="h-3.5 w-3.5 text-primary-600 flex-shrink-0" />
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 flex-shrink-0`}>Upload:</span>
      <span className={`${WIDGET_HEADER_TEXT_SIZE} text-gray-600 truncate`}>
        {fileCount} file{fileCount !== 1 ? 's' : ''}
      </span>
    </>
  );

  return (
    <CollapsibleWidget header={header} defaultExpanded={true}>
      <div className="p-4 space-y-3">
        {/* File thumbnails */}
        {uploadedFiles.length > 0 && (
          <div className="flex flex-wrap gap-3">
            {uploadedFiles.map((path, idx) => (
              <FileThumbnail key={idx} path={path} />
            ))}
          </div>
        )}

        {/* File paths */}
        <div className="space-y-1">
          {uploadedFiles.map((path, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 p-2 bg-gray-50 rounded border border-gray-200 hover:border-primary-300 hover:bg-primary-50 transition-colors cursor-pointer"
              onClick={() => openFile(path)}
              title={`Click to open ${path}`}
            >
              <div className="text-gray-500 flex-shrink-0">
                {getFileIcon(path)}
              </div>
              <code className="text-xs font-mono text-gray-700 truncate flex-1">
                {path}
              </code>
            </div>
          ))}
        </div>

        {/* Result */}
        {result && resultContent && (
          <div className={`p-2 rounded border text-xs ${
            isError
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-green-50 border-green-200 text-green-700'
          }`}>
            {resultContent}
          </div>
        )}
      </div>
    </CollapsibleWidget>
  );
};

// ============================================================================
// Widget Selector
// ============================================================================

/**
 * Select and render the appropriate widget for a tool
 */
export function renderToolWidget(props: ToolWidgetProps): React.ReactNode {
  const toolName = props.toolName?.toLowerCase();

  // Bash tool
  if (toolName === 'bash') {
    return <BashWidget {...props} />;
  }

  // Read tool
  if (toolName === 'read') {
    return <ReadWidget {...props} />;
  }

  // Write tool
  if (toolName === 'write') {
    return <WriteWidget {...props} />;
  }

  // Edit tool
  if (toolName === 'edit') {
    return <EditWidget {...props} />;
  }

  // Show File tool (supports MCP server prefixes)
  if (toolName === 'show_file' ||
      toolName === 'showfile' ||
      toolName?.includes('__show_file')) {
    return <ShowFileWidget {...props} />;
  }

  // Contact PM tool (from common_tools MCP server)
  if (toolName === 'contact_pm' || toolName === 'mcp__common_tools__contact_pm') {
    return <ContactPMWidget {...props} />;
  }

  // Contact Session tool (from pm_management MCP server)
  if (toolName === 'contact_session' || toolName === 'mcp__pm_management__contact_session') {
    return <ContactSessionWidget {...props} />;
  }

  // Spawn Session tool (from pm_management MCP server)
  if (toolName === 'spawn_instance' || toolName === 'mcp__pm_management__spawn_instance') {
    return <SpawnSessionWidget {...props} />;
  }

  // TodoWrite tool
  if (toolName === 'todowrite') {
    return <TodoWriteWidget {...props} />;
  }

  // Remind tool
  if (toolName === 'remind' || toolName === 'mcp__common_tools__remind') {
    return <RemindWidget {...props} />;
  }

  // Get Project Status tool
  if (toolName === 'get_project_status' || toolName === 'mcp__pm_management__get_project_status') {
    return <GetProjectStatusWidget {...props} />;
  }

  // Update Instance Stage tool
  if (toolName === 'update_instance_stage' || toolName === 'mcp__pm_management__update_instance_stage') {
    return <UpdateInstanceStageWidget {...props} />;
  }

  // File Upload tools (Playwright and Chrome DevTools)
  if (toolName === 'browser_file_upload' ||
      toolName === 'mcp__playwright__browser_file_upload' ||
      toolName === 'upload_file' ||
      toolName === 'mcp__chrome-devtools__upload_file') {
    return <FileUploadWidget {...props} />;
  }

  // Default widget for unknown tools
  return <DefaultToolWidget {...props} />;
}
