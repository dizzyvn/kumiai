import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { OutputPanel } from './OutputPanel';
import type { AgentInstance } from '@/lib/api';

interface OutputModalProps {
  agent: AgentInstance | null;
  onClose: () => void;
}

export function OutputModal({ agent, onClose }: OutputModalProps) {
  if (!agent) return null;

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
          className="bg-white rounded-2xl border border-gray-200 shadow-2xl w-full max-w-4xl h-[85vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{agent.character.avatar}</span>
              <div>
                <h2 className="font-bold text-lg text-gray-900">
                  {agent.character.name}
                </h2>
                <p className="text-sm text-gray-600">
                  {agent.current_session_description || 'No session description'}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Output Panel Content */}
          <div className="flex-1 overflow-hidden">
            <OutputPanel agent={agent} showHeader={true} />
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
