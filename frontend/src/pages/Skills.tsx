import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api, SkillMetadata, SkillDefinition, SkillFileNode } from '../lib/api';
import { Plus, Edit2, Trash2, Save, X, FileText, Zap, Package, Settings, Search, ChevronRight, ChevronDown, File, Folder, FileEdit, Download, AlertCircle, CheckCircle, Wrench, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { cn, components, layout } from '../styles/design-system';
import { getSkillIcon, ICON_OPTIONS } from '../constants/skillIcons';
import { SkillAssistantChat } from '../components/SkillAssistantChat';
import type { ChatContext } from '@/types/chat';
import { paths } from '@/lib/config';

interface SkillsProps {
  onChatContextChange?: (context: ChatContext) => void;
}

export default function Skills({ onChatContextChange }: SkillsProps) {
  const [skills, setSkills] = useState<SkillMetadata[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<SkillDefinition | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showIconPicker, setShowIconPicker] = useState(false);
  const iconButtonRef = useRef<HTMLButtonElement>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Mobile: local selected skill for detail view
  const [mobileSelectedSkillId, setMobileSelectedSkillId] = useState<string | null>(null);
  const [skillFiles, setSkillFiles] = useState<SkillFileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(() => {
    const saved = localStorage.getItem('isSkillChatOpen');
    return saved ? JSON.parse(saved) : false;
  });
  const [newFilePath, setNewFilePath] = useState('');
  const [isRenamingFile, setIsRenamingFile] = useState(false);
  const [renameNewPath, setRenameNewPath] = useState('');
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importSource, setImportSource] = useState('');
  const [importSkillId, setImportSkillId] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    description: '',
    category: 'general',
    license: 'MIT',
    version: '1.0.0',
    content: '',
    icon: 'zap',
    iconColor: '#4A90E2',
  });

  useEffect(() => {
    loadSkills();

    // Set chat context to skill library on mount
    if (onChatContextChange) {
      onChatContextChange({
        role: 'skill_assistant',
        name: 'Skill Library',
        description: 'Manage skills - create new skills, modify existing ones, or delete skills. Skills are stored in the skill_library directory, each with a skill.md configuration file. IMPORTANT: Skills are now pure documentation with NO tool declarations. See skill_library/_template/ for the correct file format. Each skill has category, license, and version fields in YAML frontmatter.',
        data: {
          project_path: paths.skillLibrary,
        },
      });
    }
  }, []);

  // Auto-save file content with debounce
  useEffect(() => {
    if (!selectedSkill || !selectedFile || !fileContent) return;

    const timeoutId = setTimeout(() => {
      handleFileSave();
    }, 1000); // Save after 1 second of inactivity

    return () => clearTimeout(timeoutId);
  }, [fileContent]);

  const loadSkills = async () => {
    try {
      const data = await api.getSkills();
      setSkills(data);
      // Auto-select first skill if available and nothing is selected
      if (data.length > 0 && !selectedSkill) {
        loadSkill(data[0].id);
      }
    } catch (error) {
      console.error('Failed to load skills:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSkill = async (skillId: string) => {
    try {
      const skill = await api.getSkill(skillId);
      setSelectedSkill(skill);
      setFormData({
        id: skill.id,
        name: skill.name,
        description: skill.description,
        category: skill.category || 'general',
        license: skill.license || 'MIT',
        version: skill.version || '1.0.0',
        content: skill.content,
        icon: skill.icon || 'zap',
        iconColor: skill.iconColor ?? '#4A90E2',
      });

      // Load file tree
      const files = await api.getSkillFiles(skillId);
      setSkillFiles(files);

      // Auto-select skill.md
      const skillMd = files.find(f => f.name === 'skill.md');
      if (skillMd) {
        handleFileSelect(skillId, skillMd.path);
      }
    } catch (error) {
      console.error('Failed to load skill:', error);
    }
  };

  const handleFileSelect = async (skillId: string, filePath: string) => {
    try {
      setSelectedFile(filePath);
      const result = await api.getSkillFileContent(skillId, filePath);
      setFileContent(result.content);
    } catch (error) {
      console.error('Failed to load file:', error);
    }
  };

  const handleFileSave = async () => {
    if (!selectedSkill || !selectedFile) return;

    try {
      await api.updateSkillFileContent(selectedSkill.id, selectedFile, fileContent);
    } catch (error) {
      console.error('Failed to save file:', error);
    }
  };

  const handleCreateFile = async () => {
    if (!selectedSkill || !newFilePath.trim()) return;

    try {
      // Create the file with empty content
      await api.updateSkillFileContent(selectedSkill.id, newFilePath, '');

      // Reload file tree
      const files = await api.getSkillFiles(selectedSkill.id);
      setSkillFiles(files);

      // Select the newly created file
      setSelectedFile(newFilePath);
      setFileContent('');

      // Reset new file state
      setIsCreatingFile(false);
      setNewFilePath('');
    } catch (error) {
      console.error('Failed to create file:', error);
      alert('Failed to create file');
    }
  };

  const handleDeleteFile = async () => {
    if (!selectedSkill || !selectedFile) return;
    if (selectedFile === 'skill.md') return; // Don't allow deleting skill.md

    if (!confirm(`Are you sure you want to delete "${selectedFile}"?`)) return;

    try {
      await api.deleteSkillFile(selectedSkill.id, selectedFile);

      // Reload file tree
      const files = await api.getSkillFiles(selectedSkill.id);
      setSkillFiles(files);

      // Clear selection
      setSelectedFile(null);
      setFileContent('');
    } catch (error) {
      console.error('Failed to delete file:', error);
      alert('Failed to delete file');
    }
  };

  const handleRenameFile = async () => {
    if (!selectedSkill || !selectedFile || !renameNewPath.trim()) return;

    try {
      await api.renameSkillFile(selectedSkill.id, selectedFile, renameNewPath);

      // Reload file tree
      const files = await api.getSkillFiles(selectedSkill.id);
      setSkillFiles(files);

      // Select the renamed file
      setSelectedFile(renameNewPath);

      // Reset rename state
      setIsRenamingFile(false);
      setRenameNewPath('');
    } catch (error) {
      console.error('Failed to rename file:', error);
      alert('Failed to rename file');
    }
  };

  const toggleDirectory = (path: string) => {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const generateSkillId = () => {
    return 'skill-' + Math.random().toString(36).substring(2, 10);
  };

  const handleCreate = () => {
    setIsCreating(true);
    setIsEditing(false);
    setSelectedSkill(null);
    setFormData({
      id: generateSkillId(),
      name: '',
      description: '',
      category: 'general',
      license: 'MIT',
      version: '1.0.0',
      content: '',
      icon: 'zap',
      iconColor: '#4A90E2',
    });
    // On mobile, set a placeholder to show the detail view
    if (window.innerWidth < 1024) {
      setMobileSelectedSkillId('creating');
    }
  };

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await api.createSkill({
          id: formData.id,
          name: formData.name,
          description: formData.description,
          category: formData.category,
          license: formData.license,
          version: formData.version,
          content: formData.content || undefined,
          icon: formData.icon,
          iconColor: formData.iconColor,
        });
        setIsCreating(false);
      } else if (selectedSkill) {
        // If we have a selected skill, treat it as an update (regardless of isEditing flag)
        const updatePayload = {
          name: formData.name !== selectedSkill.name ? formData.name : undefined,
          description: formData.description !== selectedSkill.description ? formData.description : undefined,
          category: formData.category !== selectedSkill.category ? formData.category : undefined,
          license: formData.license !== selectedSkill.license ? formData.license : undefined,
          version: formData.version !== selectedSkill.version ? formData.version : undefined,
          content: formData.content !== selectedSkill.content ? formData.content : undefined,
          icon: formData.icon !== selectedSkill.icon ? formData.icon : undefined,
          iconColor: formData.iconColor !== selectedSkill.iconColor ? formData.iconColor : undefined,
        };
        await api.updateSkill(selectedSkill.id, updatePayload);
        setIsEditing(false);
      }

      await loadSkills();
      if (!isCreating) {
        await loadSkill(selectedSkill!.id);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      alert('Failed to save skill: ' + errorMessage);
    }
  };

  const handleCancel = () => {
    setIsCreating(false);
    setIsEditing(false);
    if (selectedSkill) {
      setFormData({
        id: selectedSkill.id,
        name: selectedSkill.name,
        description: selectedSkill.description,
        category: selectedSkill.category || 'general',
        license: selectedSkill.license || 'MIT',
        version: selectedSkill.version || '1.0.0',
        content: selectedSkill.content,
        icon: selectedSkill.icon || 'zap',
        iconColor: selectedSkill.iconColor ?? '#4A90E2',
      });
    }
  };

  const handleDelete = async (skillId: string) => {
    if (!confirm('Are you sure you want to delete this skill?')) return;

    try {
      await api.deleteSkill(skillId);
      await loadSkills();
      if (selectedSkill?.id === skillId) {
        setSelectedSkill(null);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      alert('Failed to delete skill: ' + errorMessage);
    }
  };

  const handleImport = async () => {
    if (!importSource.trim()) {
      setImportStatus({ type: 'error', message: 'Please enter a GitHub URL or local path' });
      return;
    }

    setIsImporting(true);
    setImportStatus(null);

    try {
      const response = await api.importSkill({
        source: importSource,
        skill_id: importSkillId.trim() || undefined,
      });

      setImportStatus({ type: 'success', message: response.message || 'Skill imported successfully!' });

      // Wait a moment to show success message
      setTimeout(async () => {
        // Reload skills list
        await loadSkills();

        // Select the newly imported skill
        await loadSkill(response.skill.id);

        // Close modal and reset
        setIsImportModalOpen(false);
        setImportSource('');
        setImportSkillId('');
        setImportStatus(null);
      }, 1500);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setImportStatus({ type: 'error', message: errorMessage });
    } finally {
      setIsImporting(false);
    }
  };

  const handleOpenImportModal = () => {
    setIsImportModalOpen(true);
    setImportSource('');
    setImportSkillId('');
    setImportStatus(null);
  };

  const handleCloseImportModal = () => {
    if (!isImporting) {
      setIsImportModalOpen(false);
      setImportSource('');
      setImportSkillId('');
      setImportStatus(null);
    }
  };

  const isFormEditing = isCreating || isEditing;

  // Filter skills based on search query
  const filteredSkills = skills.filter(skill =>
    skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    skill.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    skill.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Use mobile state on mobile, regular state on desktop
  const activeSkillId = window.innerWidth < 1024 ? mobileSelectedSkillId : selectedSkill?.id;

  // Handler for selecting skill
  const handleSelectSkill = async (skillId: string) => {
    // Close chat when selecting a skill
    if (isChatOpen) {
      setIsChatOpen(false);
      localStorage.setItem('isSkillChatOpen', JSON.stringify(false));
    }

    if (window.innerWidth < 1024) {
      // Mobile: use local state
      setMobileSelectedSkillId(skillId);
      await loadSkill(skillId);
    } else {
      // Desktop: use regular selection
      await loadSkill(skillId);
    }
    setIsCreating(false);
    setIsEditing(false);
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-white">
        {/* Mobile: Skill List (when no skill selected and chat not open) */}
        {!activeSkillId && !isChatOpen && (
          <div className="flex-1 lg:hidden flex flex-col overflow-hidden">
            {/* Search Bar */}
            <div className="flex-shrink-0 p-4 bg-white">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search skills..."
                    className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  />
                </div>
                <button
                  onClick={handleCreate}
                  className="flex-shrink-0 p-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors"
                  title="New Skill"
                >
                  <Plus className="w-4 h-4" />
                </button>
                <button
                  onClick={handleOpenImportModal}
                  className="flex-shrink-0 p-2 rounded-lg bg-accent-500 text-white hover:bg-accent-600 transition-colors"
                  title="Import Skill"
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Grid Container */}
            <div className="flex-1 overflow-y-auto p-2">
              {loading ? (
                <div className="text-center py-12">
                  <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                  <p className="text-gray-500">Loading skills...</p>
                </div>
              ) : filteredSkills.length === 0 ? (
                <div className="text-center py-12">
                  <Zap className="w-12 h-12 mx-auto mb-2.5 text-gray-400" />
                  <p className="text-sm text-gray-500">{searchQuery ? 'No skills found' : 'No skills yet'}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {searchQuery ? 'Try a different search term' : 'Create one to get started'}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {filteredSkills.map((skill) => {
                    const IconComponent = getSkillIcon(skill.icon);
                    return (
                      <div
                        key={skill.id}
                        onClick={() => handleSelectSkill(skill.id)}
                        className="bg-white border-2 border-gray-200 rounded-xl p-3 cursor-pointer hover:border-primary-400 hover:shadow-md transition-all"
                      >
                        <div className="flex gap-3">
                          <div
                            className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
                            style={{ backgroundColor: skill.iconColor || '#253779' }}
                          >
                            <IconComponent className="w-6 h-6 text-white" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-base font-bold text-gray-900 truncate">{skill.name}</h3>
                            <p className="text-sm text-gray-600 line-clamp-2">{skill.description}</p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </div>
        )}

        {/* Desktop: Skill List */}
        <div className="hidden lg:flex border-r-2 border-primary-500 flex-col relative" style={{ width: layout.sidebarWidth }}>
          {/* Search Bar */}
          <div className="h-12 px-3 bg-white flex items-center flex-shrink-0">
            <div className="flex items-center gap-2 w-full">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search skills..."
                  className="w-full pl-10 pr-4 py-1.5 border border-gray-300 bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
              </div>
              <button
                onClick={() => setIsCreating(true)}
                className="flex-shrink-0 p-1.5 bg-primary-500 text-white hover:bg-primary-600 transition-colors"
                title="New Skill"
              >
                <Plus className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsImportModalOpen(true)}
                className="flex-shrink-0 p-1.5 bg-accent-500 text-white hover:bg-accent-600 transition-colors"
                title="Import Skill"
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2 pb-24">
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                <p className="text-gray-500">Loading...</p>
              </div>
            </div>
          ) : filteredSkills.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              <Zap className="w-12 h-12 mx-auto mb-2.5 text-gray-400" />
              <p className="text-sm">{searchQuery ? 'No skills found' : 'No skills yet'}</p>
              <p className="text-xs text-gray-400 mt-1">{searchQuery ? 'Try a different search term' : 'Create one to get started'}</p>
            </div>
          ) : (
            <div className="flex flex-col">
              {filteredSkills.map((skill) => (
                <div
                  key={skill.id}
                  onClick={() => handleSelectSkill(skill.id)}
                  className={cn(
                    "border-t-2 border-b-2 px-3 py-2 cursor-pointer hover:bg-primary-100 transition-all flex gap-4 min-h-[100px]",
                    selectedSkill?.id === skill.id
                      ? "border-primary-500 bg-primary-100"
                      : "border-gray-200 bg-white"
                  )}
                >
                  <div className="flex-1 flex flex-col gap-1">
                    {/* Name at top */}
                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-bold text-gray-900">
                        {skill.name}
                      </h3>
                    </div>

                    {/* Icon and Description row */}
                    <div className="flex gap-4">
                      {/* Icon */}
                      <div className="flex-shrink-0">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${skill.iconColor ? '' : 'bg-gray-100'}`}
                          style={{
                            ...(skill.iconColor && { backgroundColor: skill.iconColor }),
                            ...(selectedSkill?.id === skill.id && {
                              boxShadow: '0 0 0 2px rgb(219 234 254)'
                            })
                          }}
                          title={`Color: ${skill.iconColor || 'default'}`}
                        >
                          {(() => {
                            const IconComponent = getSkillIcon(skill.icon);
                            return <IconComponent className="w-6 h-6 text-white" />;
                          })()}
                        </div>
                      </div>

                      {/* Description */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-600 line-clamp-3">
                          {skill.description}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          </div>

        </div>

        {/* Skill Detail / Editor OR Assistant Chat */}
        <div className={cn(
          "flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-50",
          // On mobile, only show when a skill is selected or creating or chat is open
          window.innerWidth < 1024
            ? (activeSkillId || isCreating || isChatOpen ? "flex" : "hidden")
            : "flex"
        )}>
          {isChatOpen ? (
            <SkillAssistantChat
              isOpen={isChatOpen}
              onToggle={() => {
                setIsChatOpen(!isChatOpen);
                localStorage.setItem('isSkillChatOpen', JSON.stringify(!isChatOpen));
              }}
              skillId={selectedSkill?.id}
              skillPath={selectedSkill?.id ? `skill_library/${selectedSkill.id}` : undefined}
              skillName={selectedSkill?.name}
              onSkillUpdated={async () => {
                // Reload skills list and refresh current skill if one is selected
                try {
                  // Get current skills before reload
                  const skillsBefore = skills.map(s => s.id);

                  // Reload skills list from filesystem
                  const updatedSkills = await api.getSkills();
                  setSkills(updatedSkills);

                  // Detect newly created skills
                  const newSkills = updatedSkills.filter(s => !skillsBefore.includes(s.id));

                  // Determine which skill to sync and reload
                  let skillToReload = selectedSkill?.id;

                  // If a new skill was created and no skill is selected, select the new one
                  if (newSkills.length > 0 && !selectedSkill) {
                    skillToReload = newSkills[0].id;
                  }

                  // Sync and reload the skill
                  if (skillToReload) {
                    // Sync database from filesystem
                    await api.syncSkill(skillToReload);

                    // Reload skill metadata
                    const skill = await api.getSkill(skillToReload);
                    setSelectedSkill(skill);
                    setFormData({
                      id: skill.id,
                      name: skill.name,
                      description: skill.description,
                      category: skill.category || 'general',
                      license: skill.license || 'MIT',
                      version: skill.version || '1.0.0',
                      content: skill.content,
                      icon: skill.icon || 'zap',
                      iconColor: skill.iconColor ?? '#4A90E2',
                    });

                    // Reload file tree
                    const files = await api.getSkillFiles(skillToReload);
                    setSkillFiles(files);

                    // Reload currently selected file
                    if (selectedFile) {
                      const result = await api.getSkillFileContent(skillToReload, selectedFile);
                      setFileContent(result.content);
                    }
                  }
                } catch (error) {
                  console.error('Failed to reload skills:', error);
                }
              }}
            />
          ) : isCreating || selectedSkill ? (
            <>
              {/* Mobile Back Button */}
              {(activeSkillId || isCreating) && (
                <div className="lg:hidden flex-shrink-0 border-b border-gray-200 bg-white px-4 py-3">
                  <button
                    onClick={() => {
                      setMobileSelectedSkillId(null);
                      setIsCreating(false);
                      setIsEditing(false);
                    }}
                    className="flex items-center gap-2 text-gray-700 hover:text-gray-900 transition-colors"
                  >
                    <ChevronRight className="w-5 h-5 rotate-180" />
                    <span className="font-medium">Back to Skills</span>
                  </button>
                </div>
              )}

              {/* Form */}
              <div className="flex-1 overflow-y-auto px-4 lg:px-6 py-6 space-y-6 scrollbar-hide">
                {/* Basic Info Card */}
                <Card>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <button
                        ref={iconButtonRef}
                        type="button"
                        onClick={() => setShowIconPicker(!showIconPicker)}
                        className="w-8 h-8 rounded-lg border border-gray-300 hover:border-primary-400 flex items-center justify-center transition-all"
                        style={{ backgroundColor: formData.iconColor }}
                        title="Click to change icon and color"
                      >
                        {(() => {
                          const IconComponent = getSkillIcon(formData.icon);
                          return <IconComponent className="w-5 h-5 text-white" />;
                        })()}
                      </button>
                      <h3 className="text-lg font-semibold text-gray-900">Basic Information</h3>
                    </div>
                    <div className="flex gap-3">
                      <Button
                        variant="primary"
                        icon={<Save className="w-4 h-4" />}
                        onClick={handleSave}
                        size="sm"
                      >
                        Save
                      </Button>
                      {!isCreating && selectedSkill && (
                        <Button
                          variant="danger"
                          icon={<Trash2 className="w-4 h-4" />}
                          onClick={() => handleDelete(selectedSkill.id)}
                          size="sm"
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <Input
                      label="Name"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="Skill Name"
                      required
                    />

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        Description <span className="text-red-500">*</span>
                      </label>
                      <textarea
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        rows={3}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                        placeholder="Brief description of the skill's purpose"
                      />
                    </div>
                  </div>
                </Card>

                {/* Metadata Card */}
                <Card>
                  <div className="flex items-center gap-2 mb-4">
                    <Settings className="w-5 h-5 text-gray-600" />
                    <h3 className="text-lg font-semibold text-gray-900">Metadata</h3>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        Category <span className="text-red-500">*</span>
                      </label>
                      <select
                        value={formData.category}
                        onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      >
                        <option value="general">General</option>
                        <option value="productivity">Productivity</option>
                        <option value="development">Development</option>
                        <option value="data">Data & Analytics</option>
                        <option value="communication">Communication</option>
                        <option value="automation">Automation</option>
                        <option value="research">Research</option>
                        <option value="design">Design</option>
                        <option value="documentation">Documentation</option>
                        <option value="testing">Testing</option>
                        <option value="deployment">Deployment</option>
                        <option value="other">Other</option>
                      </select>
                    </div>

                    <Input
                      label="License"
                      value={formData.license}
                      onChange={(e) => setFormData({ ...formData, license: e.target.value })}
                      placeholder="MIT"
                      required
                      helperText="License for this skill (e.g., MIT, Apache-2.0, GPL-3.0)"
                    />

                    <Input
                      label="Version"
                      value={formData.version}
                      onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                      placeholder="1.0.0"
                      required
                      helperText="Semantic version (e.g., 1.0.0, 2.1.3)"
                    />
                  </div>
                </Card>

                {/* Advanced Card - File Tree & Editor */}
                <Card>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-gray-600" />
                      <h3 className="text-lg font-semibold text-gray-900">Files</h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<Plus className="w-4 h-4" />}
                        onClick={() => setIsCreatingFile(true)}
                      >
                        New File
                      </Button>
                      {selectedFile && selectedFile !== 'skill.md' && (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            icon={<FileEdit className="w-4 h-4" />}
                            onClick={() => {
                              setIsRenamingFile(true);
                              setRenameNewPath(selectedFile);
                            }}
                          >
                            Rename
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            icon={<Trash2 className="w-4 h-4" />}
                            onClick={handleDeleteFile}
                          >
                            Delete
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* New File Input */}
                  {isCreatingFile && (
                    <div className="mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="flex items-center gap-2">
                        <Input
                          value={newFilePath}
                          onChange={(e) => setNewFilePath(e.target.value)}
                          placeholder="path/to/newfile.md"
                          className="flex-1"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              handleCreateFile();
                            } else if (e.key === 'Escape') {
                              setIsCreatingFile(false);
                              setNewFilePath('');
                            }
                          }}
                        />
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={handleCreateFile}
                          disabled={!newFilePath.trim()}
                        >
                          Create
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<X className="w-4 h-4" />}
                          onClick={() => {
                            setIsCreatingFile(false);
                            setNewFilePath('');
                          }}
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-2">
                        Enter file path (e.g., "docs/guide.md" or "script.py")
                      </p>
                    </div>
                  )}

                  {/* Rename File Input */}
                  {isRenamingFile && (
                    <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                      <div className="flex items-center gap-2">
                        <Input
                          value={renameNewPath}
                          onChange={(e) => setRenameNewPath(e.target.value)}
                          placeholder="new/path/filename.md"
                          className="flex-1"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              handleRenameFile();
                            } else if (e.key === 'Escape') {
                              setIsRenamingFile(false);
                              setRenameNewPath('');
                            }
                          }}
                        />
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={handleRenameFile}
                          disabled={!renameNewPath.trim() || renameNewPath === selectedFile}
                        >
                          Rename
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<X className="w-4 h-4" />}
                          onClick={() => {
                            setIsRenamingFile(false);
                            setRenameNewPath('');
                          }}
                        />
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        Renaming: {selectedFile} → {renameNewPath}
                      </p>
                    </div>
                  )}

                  <div className="flex gap-4 h-[700px]">
                    {/* File Tree */}
                    <div className="w-64 border-r-2 border-primary-500 pr-4 overflow-y-auto scrollbar-hide">
                      <FileTree
                        nodes={skillFiles}
                        selectedFile={selectedFile}
                        expandedDirs={expandedDirs}
                        onFileSelect={(path) => handleFileSelect(selectedSkill!.id, path)}
                        onToggleDir={toggleDirectory}
                      />
                    </div>

                    {/* File Editor */}
                    <div className="flex-1 flex flex-col">
                      {selectedFile ? (
                        <>
                          <div className="flex items-center gap-2 mb-2 text-sm text-gray-600">
                            <File className="w-4 h-4" />
                            <span className="font-mono">{selectedFile}</span>
                          </div>
                          <textarea
                            value={fileContent}
                            onChange={(e) => setFileContent(e.target.value)}
                            className="flex-1 w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 font-mono text-sm transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none scrollbar-hide"
                          />
                        </>
                      ) : (
                        <div className="flex-1 flex items-center justify-center text-gray-400">
                          <div className="text-center">
                            <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">Select a file to edit</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              </div>
            </>
          ) : loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                <p className="text-gray-500">Loading...</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Zap className="w-8 h-8 mx-auto mb-4 text-gray-400" />
                <p className="text-lg font-medium text-gray-900">Select a skill to view details</p>
                <p className="text-sm text-gray-500 mt-1">or create a new one to get started</p>
              </div>
            </div>
          )}
        </div>

        {/* Import Modal */}
        <AnimatePresence>
          {isImportModalOpen && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 bg-black/50 z-40"
                onClick={handleCloseImportModal}
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2 }}
                className="fixed inset-0 flex items-center justify-center z-50 p-4"
                onClick={(e) => e.stopPropagation()}
              >
                <Card className="w-full max-w-2xl bg-white shadow-2xl">
                  {/* Header */}
                  <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary-100 flex items-center justify-center">
                        <Download className="w-6 h-6 text-primary-600" />
                      </div>
                      <div>
                        <h2 className="text-xl font-bold text-gray-900">Import Skill</h2>
                        <p className="text-sm text-gray-500">Import a skill from GitHub or local path</p>
                      </div>
                    </div>
                    <button
                      onClick={handleCloseImportModal}
                      disabled={isImporting}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                    >
                      <X className="w-5 h-5 text-gray-500" />
                    </button>
                  </div>

                  {/* Form */}
                  <div className="space-y-5">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Source URL or Path <span className="text-red-500">*</span>
                      </label>
                      <Input
                        value={importSource}
                        onChange={(e) => setImportSource(e.target.value)}
                        placeholder="https://github.com/user/repo/tree/branch/.claude/skills/skill-name"
                        disabled={isImporting}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !isImporting) {
                            handleImport();
                          }
                        }}
                      />
                      <p className="text-xs text-gray-500 mt-2">
                        Examples:<br />
                        • Anthropic Skills: <code className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">https://github.com/anthropics/skills/tree/main/skills/internal-comms</code><br />
                        • Custom: <code className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">https://github.com/user/repo/tree/branch/.claude/skills/skill-name</code><br />
                        • Local: <code className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">/path/to/skill/directory</code>
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Custom Skill ID <span className="text-gray-400">(Optional)</span>
                      </label>
                      <Input
                        value={importSkillId}
                        onChange={(e) => setImportSkillId(e.target.value)}
                        placeholder="my-custom-skill-id"
                        disabled={isImporting}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !isImporting) {
                            handleImport();
                          }
                        }}
                      />
                      <p className="text-xs text-gray-500 mt-2">
                        Leave empty to auto-generate or use the skill's existing ID
                      </p>
                    </div>

                    {/* Status Message */}
                    {importStatus && (
                      <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={cn(
                          "flex items-start gap-3 p-4 rounded-lg",
                          importStatus.type === 'success'
                            ? "bg-green-50 border border-green-200"
                            : "bg-red-50 border border-red-200"
                        )}
                      >
                        {importStatus.type === 'success' ? (
                          <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                        ) : (
                          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                        )}
                        <div className="flex-1">
                          <p className={cn(
                            "text-sm font-medium",
                            importStatus.type === 'success' ? "text-green-900" : "text-red-900"
                          )}>
                            {importStatus.type === 'success' ? 'Success!' : 'Error'}
                          </p>
                          <p className={cn(
                            "text-sm mt-1",
                            importStatus.type === 'success' ? "text-green-700" : "text-red-700"
                          )}>
                            {importStatus.message}
                          </p>
                        </div>
                      </motion.div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex gap-3 mt-6 pt-6 border-t border-gray-200">
                    <Button
                      variant="secondary"
                      onClick={handleCloseImportModal}
                      disabled={isImporting}
                      className="flex-1"
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="primary"
                      icon={<Download className="w-4 h-4" />}
                      onClick={handleImport}
                      disabled={isImporting || !importSource.trim()}
                      loading={isImporting}
                      className="flex-1"
                    >
                      {isImporting ? 'Importing...' : 'Import'}
                    </Button>
                  </div>
                </Card>
              </motion.div>
            </>
          )}
        </AnimatePresence>

        {/* Icon Picker Popup */}
        <AnimatePresence>
          {showIconPicker && iconButtonRef.current && (
            <>
              {/* Invisible overlay to close on outside click */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowIconPicker(false)}
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -10 }}
                transition={{ duration: 0.15 }}
                className="fixed z-50 bg-white rounded-xl border border-gray-200 shadow-xl p-5 w-96"
                style={{
                  top: `${iconButtonRef.current.getBoundingClientRect().bottom + 8}px`,
                  left: `${iconButtonRef.current.getBoundingClientRect().left}px`,
                }}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-bold text-gray-900">Select Icon</h3>
                  <button
                    onClick={() => setShowIconPicker(false)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>

                {/* Icon Grid */}
                <div className="grid grid-cols-6 gap-2 mb-4">
                  {ICON_OPTIONS.map(({ value, label, Icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => {
                        setFormData({ ...formData, icon: value });
                      }}
                      className={cn(
                        "aspect-square p-3 rounded-lg border-2 flex items-center justify-center transition-all hover:border-primary-400 hover:bg-primary-50",
                        formData.icon === value
                          ? "border-primary-500 bg-primary-50 shadow-sm"
                          : "border-gray-200 bg-white"
                      )}
                      title={label}
                    >
                      <Icon className={cn(
                        "w-6 h-6 transition-colors",
                        formData.icon === value ? "text-primary-600" : "text-gray-600"
                      )} />
                    </button>
                  ))}
                </div>

                {/* Separator */}
                <div className="border-t border-gray-200 mb-4"></div>

                {/* Color Selector */}
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-gray-700">
                    Icon Background Color
                  </label>
                  <div className="grid grid-cols-8 gap-1.5">
                    {[
                      '#4A90E2', // blue
                      '#E24A90', // pink
                      '#90E24A', // green
                      '#E2904A', // orange
                      '#4AE290', // teal
                      '#904AE2', // purple
                      '#E2E24A', // yellow
                      '#4A4AE2', // indigo
                      '#E24A4A', // red
                      '#4AE2E2', // cyan
                      '#8B5CF6', // violet
                      '#10B981', // emerald
                      '#F59E0B', // amber
                      '#EF4444', // crimson
                      '#EC4899', // magenta
                      '#78716c', // stone
                    ].map((color) => (
                      <button
                        key={color}
                        type="button"
                        onClick={() => setFormData({ ...formData, iconColor: color })}
                        className={cn(
                          "w-7 h-7 rounded-md border-2 transition-all hover:scale-110",
                          formData.iconColor === color
                            ? "border-gray-900 ring-2 ring-offset-1 ring-gray-400"
                            : "border-gray-200"
                        )}
                        style={{ backgroundColor: color }}
                        title={color}
                      />
                    ))}
                  </div>

                  {/* Custom Color Input */}
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={formData.iconColor}
                      onChange={(e) => setFormData({ ...formData, iconColor: e.target.value })}
                      className="w-12 h-10 rounded-lg border border-gray-300 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={formData.iconColor}
                      onChange={(e) => setFormData({ ...formData, iconColor: e.target.value })}
                      placeholder="#4A90E2"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                    />
                  </div>
                </div>

                {/* Done Button */}
                <button
                  onClick={() => setShowIconPicker(false)}
                  className="w-full mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium"
                >
                  Done
                </button>
              </motion.div>
            </>
          )}
        </AnimatePresence>

      {/* Skill Assistant Chat Toggle Button */}
      {!isChatOpen && (
        <button
          onClick={() => {
            setIsChatOpen(true);
            localStorage.setItem('isSkillChatOpen', JSON.stringify(true));
          }}
          className="fixed bottom-20 lg:bottom-6 right-6 w-14 h-14 bg-white border border-gray-200 hover:bg-gray-50 rounded-full shadow-md flex items-center justify-center transition-colors z-50"
          aria-label="Open skill assistant chat"
          title="Talk to your Skill Assistant"
        >
          <Wrench className="w-6 h-6 text-gray-600" />
        </button>
      )}
    </div>
  );
}

// FileTree Component
interface FileTreeProps {
  nodes: SkillFileNode[];
  selectedFile: string | null;
  expandedDirs: Set<string>;
  onFileSelect: (path: string) => void;
  onToggleDir: (path: string) => void;
  level?: number;
}

function FileTree({ nodes, selectedFile, expandedDirs, onFileSelect, onToggleDir, level = 0 }: FileTreeProps) {
  return (
    <div className="space-y-0.5">
      {nodes.map((node) => (
        <div key={node.path}>
          {node.type === 'directory' ? (
            <>
              <button
                onClick={() => onToggleDir(node.path)}
                className="flex items-center gap-1 w-full px-2 py-1 text-sm text-left hover:bg-gray-100 rounded transition-colors"
                style={{ paddingLeft: `${level * 12 + 8}px` }}
              >
                {expandedDirs.has(node.path) ? (
                  <ChevronDown className="w-4 h-4 text-gray-500" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-500" />
                )}
                <Folder className="w-4 h-4 text-yellow-600" />
                <span className="text-gray-700">{node.name}</span>
              </button>
              {expandedDirs.has(node.path) && node.children && (
                <FileTree
                  nodes={node.children}
                  selectedFile={selectedFile}
                  expandedDirs={expandedDirs}
                  onFileSelect={onFileSelect}
                  onToggleDir={onToggleDir}
                  level={level + 1}
                />
              )}
            </>
          ) : (
            <button
              onClick={() => onFileSelect(node.path)}
              className={cn(
                "flex items-center gap-1 w-full px-2 py-1 text-sm text-left rounded transition-colors",
                selectedFile === node.path
                  ? "bg-primary-100 text-primary-900"
                  : "hover:bg-gray-100 text-gray-700"
              )}
              style={{ paddingLeft: `${level * 12 + 28}px` }}
            >
              <File className="w-4 h-4" />
              <span>{node.name}</span>
              {node.size !== undefined && (
                <span className="ml-auto text-xs text-gray-400">
                  {formatFileSize(node.size)}
                </span>
              )}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}
