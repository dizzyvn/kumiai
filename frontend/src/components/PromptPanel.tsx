import { useState } from 'react';
import { Sparkles, Send, Loader2, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface PromptPanelProps {
  title: string;
  placeholder: string;
  onSubmit: (prompt: string) => Promise<{ agent_id: string; message: string }>;
  isOpen: boolean;
  onClose: () => void;
}

export function PromptPanel({ title, placeholder, onSubmit, isOpen, onClose }: PromptPanelProps) {
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const result = await onSubmit(prompt);
      setAgentId(result.agent_id);
      setMessage(result.message);
      setPrompt('');

      // Auto-close after 3 seconds
      setTimeout(() => {
        handleClose();
      }, 3000);
    } catch (error: any) {
      alert('Failed to process request: ' + error.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setPrompt('');
    setAgentId(null);
    setMessage(null);
    setIsSubmitting(false);
    onClose();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-2xl z-50"
        >
          <div className="max-w-4xl mx-auto p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg">
                  <Sparkles className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">{title}</h3>
                  <p className="text-sm text-gray-500">
                    Ask Claude Code to help you
                  </p>
                </div>
              </div>
              <button
                onClick={handleClose}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Result Message */}
            {message && agentId && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg"
              >
                <p className="text-sm text-green-800">
                  ✓ {message}
                </p>
                <p className="text-xs text-green-600 mt-1">
                  Agent ID: {agentId} - Check the Agents tab to monitor progress
                </p>
              </motion.div>
            )}

            {/* Input Area */}
            <div className="flex gap-3">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handleSubmit();
                  }
                }}
                placeholder={placeholder}
                disabled={isSubmitting}
                rows={3}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 disabled:bg-gray-50 disabled:text-gray-500 resize-none"
              />
              <button
                onClick={handleSubmit}
                disabled={!prompt.trim() || isSubmitting}
                className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:from-purple-600 hover:to-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-5 h-5" />
                    <span>Send</span>
                  </>
                )}
              </button>
            </div>

            {/* Hint */}
            <p className="text-xs text-gray-500 mt-2">
              Press <kbd className="px-2 py-1 bg-gray-100 rounded text-xs">⌘ + Enter</kbd> or <kbd className="px-2 py-1 bg-gray-100 rounded text-xs">Ctrl + Enter</kbd> to send
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
