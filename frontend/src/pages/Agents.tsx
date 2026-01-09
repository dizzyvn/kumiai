import { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  api,
  CharacterMetadata,
  CharacterDefinition,
  CharacterCapabilities,
  SkillFileNode
} from '../lib/api';
import type { ChatContext } from '@/types/chat';
import { Plus, Edit2, Trash2, Save, X, User, Settings, RefreshCw, Cpu, Package, Search, ChevronRight, ChevronDown, File, Folder, FileText, FileEdit, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { Avatar } from '../components/Avatar';
import { SkillSelector } from '../components/SkillSelector';
import { McpServerSelector } from '../components/McpServerSelector';
import { CharacterAssistantChat } from '../components/CharacterAssistantChat';
import { cn, components, layout } from '../styles/design-system';
import { getSkillIcon } from '../constants/skillIcons';
import { paths } from '@/lib/config';

interface AgentsProps {
  onChatContextChange?: (context: ChatContext) => void;
}

export default function Agents({ onChatContextChange }: AgentsProps) {
  const [characters, setCharacters] = useState<CharacterMetadata[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterDefinition | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);

  // Mobile: local selected character for detail view
  const [mobileSelectedCharacterId, setMobileSelectedCharacterId] = useState<string | null>(null);
  const [availableSkills, setAvailableSkills] = useState<{ id: string; name: string; description: string; icon?: string; iconColor?: string }[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [availableMcpServers, setAvailableMcpServers] = useState<any[]>([]);
  const [selectedMcpServers, setSelectedMcpServers] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [characterFiles, setCharacterFiles] = useState<SkillFileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [newFilePath, setNewFilePath] = useState('');
  const [isRenamingFile, setIsRenamingFile] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(() => {
    const saved = localStorage.getItem('isCharacterChatOpen');
    return saved ? JSON.parse(saved) : false;
  });
  const [renameNewPath, setRenameNewPath] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    default_model: 'sonnet',
    personality: '',
    color: '#4A90E2',
    avatar: '🤖',
  });

  useEffect(() => {
    loadCharacters();
    loadAvailableSkills();
    loadAvailableMcpServers();

    // Set chat context to agents library on mount
    if (onChatContextChange) {
      onChatContextChange({
        role: 'character_assistant',
        name: 'Agent Library',
        description: 'Manage team members - create new agents, modify existing ones, or delete agents. Agents are stored in the character_library directory, each with an agent.md configuration file. IMPORTANT: See character_library/_template/ for the correct file format and examples. Always use YAML frontmatter format. DO NOT add or modify the "avatar:" field unless the user explicitly asks - it is auto-generated. NOTE: Agent capabilities (tools, MCP servers, skills) are stored in the DATABASE, NOT in the agent.md file. The agent.md file contains ONLY personality and system prompt content.',
        data: {
          project_path: paths.characterLibrary,
        },
      });
    }
  }, []);

  // Auto-save file content with debounce
  useEffect(() => {
    if (!selectedCharacter || !selectedFile || !fileContent) return;

    const timeoutId = setTimeout(() => {
      handleFileSave();
    }, 1000); // Save after 1 second of inactivity

    return () => clearTimeout(timeoutId);
  }, [fileContent]);

  const loadAvailableSkills = async () => {
    try {
      const skills = await api.getSkills();
      setAvailableSkills(skills);
    } catch (error) {
      console.error('Failed to load skills:', error);
    }
  };

  const loadAvailableMcpServers = async () => {
    try {
      const servers = await api.getMcpServers();
      setAvailableMcpServers(servers);
    } catch (error) {
      console.error('Failed to load MCP servers:', error);
    }
  };

  const loadCharacters = async () => {
    try {
      const data = await api.getCharactersLibrary();
      setCharacters(data);
      // Auto-select first character if available and nothing is selected
      if (data.length > 0 && !selectedCharacter) {
        loadCharacter(data[0].id);
      }
    } catch (error) {
      console.error('Failed to load characters:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadCharacter = async (characterId: string) => {
    try {
      const character = await api.getCharacterLibrary(characterId);
      setSelectedCharacter(character);
      setFormData({
        name: character.name,
        description: character.description,
        default_model: character.default_model,
        personality: character.personality || '',
        color: character.color,
        avatar: character.avatar,
      });
      setSelectedSkills(character.capabilities?.allowed_skills || []);
      setSelectedMcpServers(character.capabilities?.allowed_mcp_servers || []);

      // Load file tree
      try {
        const files = await api.getCharacterFiles(characterId);
        setCharacterFiles(files);

        // Auto-select agent.md if it exists
        const agentMd = files.find(f => f.name === 'agent.md');
        if (agentMd) {
          handleFileSelect(characterId, agentMd.path);
        } else {
          setSelectedFile(null);
          setFileContent('');
        }
      } catch (error) {
        // Character might not have a directory yet
        setCharacterFiles([]);
        setSelectedFile(null);
        setFileContent('');
      }
    } catch (error) {
      console.error('Failed to load character:', error);
    }
  };

  const handleFileSelect = async (characterId: string, filePath: string) => {
    try {
      setSelectedFile(filePath);
      const result = await api.getCharacterFileContent(characterId, filePath);
      setFileContent(result.content);
    } catch (error) {
      console.error('Failed to load file:', error);
    }
  };

  const handleFileSave = async () => {
    if (!selectedCharacter || !selectedFile) return;

    try {
      await api.updateCharacterFileContent(selectedCharacter.id, selectedFile, fileContent);
    } catch (error) {
      console.error('Failed to save file:', error);
    }
  };

  const handleCreateFile = async () => {
    if (!selectedCharacter || !newFilePath.trim()) return;

    try {
      // Create the file with empty content
      await api.updateCharacterFileContent(selectedCharacter.id, newFilePath, '');

      // Reload file tree
      const files = await api.getCharacterFiles(selectedCharacter.id);
      setCharacterFiles(files);

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
    if (!selectedCharacter || !selectedFile) return;
    if (selectedFile === 'agent.md') return; // Don't allow deleting agent.md

    // Don't allow deleting skill directories or files within them
    const skillIds = selectedCharacter.capabilities?.allowed_skills || [];
    const isSkillPath = skillIds.some(skillId =>
      selectedFile === skillId || selectedFile.startsWith(`${skillId}/`)
    );

    if (isSkillPath) {
      alert('Cannot delete skill directories or files. Manage skills from the Skills page.');
      return;
    }

    if (!confirm(`Are you sure you want to delete "${selectedFile}"?`)) return;

    try {
      await api.deleteCharacterFile(selectedCharacter.id, selectedFile);

      // Reload file tree
      const files = await api.getCharacterFiles(selectedCharacter.id);
      setCharacterFiles(files);

      // Clear selection
      setSelectedFile(null);
      setFileContent('');
    } catch (error) {
      console.error('Failed to delete file:', error);
      alert('Failed to delete file');
    }
  };

  const handleRenameFile = async () => {
    if (!selectedCharacter || !selectedFile || !renameNewPath.trim()) return;

    try {
      await api.renameCharacterFile(selectedCharacter.id, selectedFile, renameNewPath);

      // Reload file tree
      const files = await api.getCharacterFiles(selectedCharacter.id);
      setCharacterFiles(files);

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

  const handleCreate = () => {
    setIsCreating(true);
    setIsEditing(false);
    setSelectedCharacter(null);
    setSelectedSkills([]);
    setSelectedMcpServers([]);
    setFormData({
      name: '',
      description: '',
      default_model: 'sonnet',
      personality: '',
      color: generateRandomColor(),
      avatar: generateRandomAvatar(),
    });
    // On mobile, set a placeholder to show the detail view
    if (window.innerWidth < 1024) {
      setMobileSelectedCharacterId('creating');
    }
  };

  const generateRandomColor = () => {
    const colors = [
      "#4A90E2", "#E24A90", "#90E24A", "#E2904A",
      "#4AE290", "#904AE2", "#E2E24A", "#4A4AE2",
      "#E24A4A", "#4AE2E2", "#8B5CF6", "#10B981",
    ];
    return colors[Math.floor(Math.random() * colors.length)];
  };

  const generateRandomAvatar = () => {
    // Generate random string to use as avatar seed
    return Math.random().toString(36).substring(2, 10);
  };

  const handleRegenerateAvatar = () => {
    setFormData({
      ...formData,
      color: generateRandomColor(),
      avatar: generateRandomAvatar()
    });
  };

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleSave = async () => {
    try {
      // Validation
      if (!formData.name.trim()) {
        alert('Agent name is required');
        return;
      }
      if (!formData.description.trim()) {
        alert('Agent description is required');
        return;
      }

      if (isCreating) {
        const result = await api.createCharacter({
          name: formData.name,
          description: formData.description,
          default_model: formData.default_model,
          color: formData.color,
          avatar: formData.avatar,
          personality: formData.personality || undefined,
          capabilities: {
            allowed_tools: [],
            allowed_mcp_servers: selectedMcpServers,
            allowed_skills: selectedSkills,
            allowed_agents: [],
            allowed_slash_commands: [],
          },
        });
        setIsCreating(false);
      } else if (selectedCharacter) {
        // If we have a selected character, treat it as an update (regardless of isEditing flag)
        const updateData = {
          name: formData.name !== selectedCharacter.name ? formData.name : undefined,
          description: formData.description !== selectedCharacter.description ? formData.description : undefined,
          default_model: formData.default_model !== selectedCharacter.default_model ? formData.default_model : undefined,
          color: formData.color !== selectedCharacter.color ? formData.color : undefined,
          avatar: formData.avatar !== selectedCharacter.avatar ? formData.avatar : undefined,
          personality: formData.personality !== (selectedCharacter.personality || '') ? formData.personality || undefined : undefined,
          capabilities: (
            JSON.stringify(selectedMcpServers) !== JSON.stringify(selectedCharacter.capabilities?.allowed_mcp_servers || []) ||
            JSON.stringify(selectedSkills) !== JSON.stringify(selectedCharacter.capabilities?.allowed_skills || [])
          ) ? {
            allowed_tools: [],
            allowed_mcp_servers: selectedMcpServers,
            allowed_skills: selectedSkills,
            allowed_agents: selectedCharacter.capabilities?.allowed_agents || [],
            allowed_slash_commands: selectedCharacter.capabilities?.allowed_slash_commands || [],
          } : undefined,
        };
        await api.updateCharacter(selectedCharacter.id, updateData);
        setIsEditing(false);
      }

      await loadCharacters();
      if (!isCreating) {
        await loadCharacter(selectedCharacter!.id);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : JSON.stringify(error);
      console.error('Error saving character:', error);
      alert('Failed to save character: ' + errorMessage);
    }
  };

  const handleCancel = () => {
    setIsCreating(false);
    setIsEditing(false);
    if (selectedCharacter) {
      setFormData({
        name: selectedCharacter.name,
        description: selectedCharacter.description,
        default_model: selectedCharacter.default_model,
        personality: selectedCharacter.personality || '',
        color: selectedCharacter.color,
        avatar: selectedCharacter.avatar,
      });
      setSelectedSkills(selectedCharacter.capabilities?.allowed_skills || []);
      setSelectedMcpServers(selectedCharacter.capabilities?.allowed_mcp_servers || []);
    }
  };

  const handleDelete = async (characterId: string) => {
    if (!confirm('Are you sure you want to delete this character?')) return;

    try {
      await api.deleteCharacter(characterId);
      await loadCharacters();
      if (selectedCharacter?.id === characterId) {
        setSelectedCharacter(null);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      alert('Failed to delete character: ' + errorMessage);
    }
  };

  const addSkill = (skillId: string) => {
    if (!selectedSkills.includes(skillId)) {
      setSelectedSkills(prev => [...prev, skillId]);
    }
  };

  const removeSkill = (skillId: string) => {
    setSelectedSkills(prev => prev.filter(id => id !== skillId));
  };

  const addMcpServer = (serverId: string) => {
    if (!selectedMcpServers.includes(serverId)) {
      setSelectedMcpServers(prev => [...prev, serverId]);
    }
  };

  const removeMcpServer = (serverId: string) => {
    setSelectedMcpServers(prev => prev.filter(id => id !== serverId));
  };

  // Filter characters based on search query
  const filteredCharacters = characters.filter(char =>
    char.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    char.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Use mobile state on mobile, regular state on desktop
  const activeCharacterId = window.innerWidth < 1024 ? mobileSelectedCharacterId : selectedCharacter?.id;

  // Handler for selecting character
  const handleSelectCharacter = async (charId: string) => {
    // Close chat when selecting a character
    if (isChatOpen) {
      setIsChatOpen(false);
      localStorage.setItem('isCharacterChatOpen', JSON.stringify(false));
    }

    if (window.innerWidth < 1024) {
      // Mobile: use local state
      setMobileSelectedCharacterId(charId);
      await loadCharacter(charId);
    } else {
      // Desktop: use regular selection
      await loadCharacter(charId);
    }
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-white">
      {/* Mobile: Character List (when no character selected and chat not open) */}
      {!activeCharacterId && !isChatOpen && (
        <div className="flex-1 lg:hidden flex flex-col overflow-hidden">
          {/* Search Bar */}
          <div className="h-12 px-2 bg-white flex items-center flex-shrink-0">
            <div className="flex items-center gap-2 w-full">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search agents..."
                  className="w-full pl-10 pr-4 py-1.5 border border-gray-300 bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
              </div>
              <button
                onClick={handleCreate}
                className="flex-shrink-0 p-1.5 bg-primary-500 text-white hover:bg-primary-600 transition-colors"
                title="New Member"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Grid Container */}
          <div className="flex-1 overflow-y-auto p-2">
            {loading ? (
              <div className="text-center py-12">
                <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
                <p className="text-gray-500">Loading agents...</p>
              </div>
            ) : filteredCharacters.length === 0 ? (
              <div className="text-center py-12">
                <User className="w-12 h-12 mx-auto mb-2.5 text-gray-400" />
                <p className="text-sm text-gray-500">{searchQuery ? 'No agents found' : 'No agents yet'}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {searchQuery ? 'Try a different search term' : 'Create one to get started'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                {filteredCharacters.map((char) => (
                  <div
                    key={char.id}
                    onClick={() => handleSelectCharacter(char.id)}
                    className="bg-white border-2 border-gray-200 rounded-xl p-3 cursor-pointer hover:border-primary-400 hover:shadow-md transition-all"
                  >
                    <div className="flex gap-3">
                      <Avatar seed={char.avatar || char.id} size={48} className="w-12 h-12" color={char.color} />
                      <div className="flex-1 min-w-0">
                        <h3 className="text-base font-bold text-gray-900 truncate">{char.name}</h3>
                        <p className="text-sm text-gray-600 line-clamp-2">{char.description}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      )}

      {/* Left: Thumbnail Grid - Desktop only */}
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
                placeholder="Search agents..."
                className="w-full pl-10 pr-4 py-1.5 border border-gray-300 bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
              />
            </div>
            <button
              onClick={() => setIsCreating(true)}
              className="flex-shrink-0 p-1.5 bg-primary-500 text-white hover:bg-primary-600 transition-colors"
              title="Create Agent"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Grid Container */}
        <div className="flex-1 overflow-y-auto p-2 pb-24">
        {loading ? (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 mx-auto mb-3 text-gray-400 animate-spin" />
            <p className="text-gray-500">Loading characters...</p>
          </div>
        ) : filteredCharacters.length === 0 ? (
          <div className="text-center py-12">
            <User className="w-8 h-8 mx-auto mb-4 text-gray-400" />
            <p className="text-lg font-medium text-gray-900">{searchQuery ? 'No agents found' : 'No characters yet'}</p>
            <p className="text-sm text-gray-500 mt-1">{searchQuery ? 'Try a different search term' : 'Create your first character to get started'}</p>
          </div>
        ) : (
          <div className="flex flex-col">
            {filteredCharacters.map((char) => (
              <motion.div
                key={char.id}
                whileHover={{ scale: 1.01 }}
                onClick={() => {
                  handleSelectCharacter(char.id);
                  setIsCreating(false);
                  setIsEditing(false);
                }}
                className={cn(
                  "border-t-2 border-b-2 px-3 py-2 cursor-pointer hover:bg-primary-100 transition-all flex gap-4 min-h-[100px]",
                  selectedCharacter?.id === char.id
                    ? "border-primary-500 bg-primary-100"
                    : "border-gray-200 bg-white"
                )}
              >
                <div className="flex-1 flex flex-col gap-1">
                  {/* Name at top */}
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-bold text-gray-900">
                      {char.name}
                    </h3>

                    {/* Skill badges */}
                    {(char.skills?.length || 0) > 0 ? (
                      <div className="flex items-center -space-x-1">
                        {char.skills!.slice(0, 5).map((skillId) => {
                          const skill = availableSkills.find(s => s.id === skillId);
                          const IconComponent = getSkillIcon(skill?.icon);
                          return (
                            <div
                              key={skillId}
                              className={`w-6 h-6 rounded-full flex items-center justify-center ring-2 ring-white transition-all ${skill?.iconColor ? '' : 'bg-gray-100'}`}
                              style={skill?.iconColor ? { backgroundColor: skill.iconColor } : undefined}
                              title={skill?.name || skillId}
                            >
                              <IconComponent className="w-3 h-3 text-white" />
                            </div>
                          );
                        })}
                        {(char.skills?.length || 0) > 5 && (
                          <div className={cn(
                            "w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ring-2 ring-white",
                            selectedCharacter?.id === char.id
                              ? "bg-primary-200 text-primary-700"
                              : "bg-gray-200 text-gray-600"
                          )}>
                            +{(char.skills?.length || 0) - 5}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="px-3 py-1 text-xs rounded-full font-semibold bg-gray-200 text-gray-700">
                        No skills
                      </span>
                    )}
                  </div>

                  {/* Avatar and Description row */}
                  <div className="flex gap-4">
                    {/* Avatar */}
                    <div className="flex-shrink-0">
                      <Avatar
                        seed={char.avatar || char.id}
                        size={64}
                        className={cn(
                          "w-8 h-8 transition-all",
                          selectedCharacter?.id === char.id && "ring-2 ring-primary-200"
                        )}
                        color={char.color || '#4A90E2'}
                      />
                    </div>

                    {/* Description */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-600 line-clamp-3">
                        {char.description}
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
        </div>

      </div>

      {/* Right: Character Detail OR Assistant Chat */}
      <div className={cn(
        "flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-50",
        // On mobile, only show when a character is selected or creating or chat is open
        window.innerWidth < 1024
          ? (activeCharacterId || isCreating || isChatOpen ? "flex" : "hidden")
          : "flex"
      )}>
        {isChatOpen ? (
          <CharacterAssistantChat
            isOpen={isChatOpen}
            onToggle={() => {
              setIsChatOpen(!isChatOpen);
              localStorage.setItem('isCharacterChatOpen', JSON.stringify(!isChatOpen));
            }}
            characterId={selectedCharacter?.id}
            characterName={selectedCharacter?.name}
            onCharacterUpdated={async () => {
              // Reload characters list and refresh current character if one is selected
              try {
                // Get current characters before reload
                const charactersBefore = characters.map(c => c.id);

                // Reload characters list from filesystem
                const updatedCharacters = await api.getCharactersLibrary();
                setCharacters(updatedCharacters);

                // Detect newly created characters
                const newCharacters = updatedCharacters.filter(c => !charactersBefore.includes(c.id));

                // Determine which character to sync and reload
                let characterToReload = selectedCharacter?.id;

                // If a new character was created and no character is selected, select the new one
                if (newCharacters.length > 0 && !selectedCharacter) {
                  characterToReload = newCharacters[0].id;
                }

                // Sync and reload the character
                if (characterToReload) {
                  // Sync database from filesystem
                  await api.syncCharacter(characterToReload);

                  // Reload character metadata
                  const character = await api.getCharacterLibrary(characterToReload);
                  setSelectedCharacter(character);
                  setFormData({
                    name: character.name,
                    description: character.description,
                    default_model: character.default_model,
                    personality: character.personality || '',
                    color: character.color,
                    avatar: character.avatar,
                  });
                  setSelectedSkills(character.capabilities?.allowed_skills || []);

                  // Reload file tree
                  const files = await api.getCharacterFiles(characterToReload);
                  setCharacterFiles(files);

                  // Reload currently selected file
                  if (selectedFile) {
                    const result = await api.getCharacterFileContent(characterToReload, selectedFile);
                    setFileContent(result.content);
                  }
                }
              } catch (error) {
                console.error('Failed to reload characters:', error);
              }
            }}
          />
        ) : isCreating || selectedCharacter ? (
          <>
            {/* Mobile Back Button */}
            {(activeCharacterId || isCreating) && (
              <div className="lg:hidden flex-shrink-0 border-b border-gray-200 bg-white px-4 py-3">
                <button
                  onClick={() => {
                    setMobileSelectedCharacterId(null);
                    setIsCreating(false);
                    setIsEditing(false);
                  }}
                  className="flex items-center gap-2 text-gray-700 hover:text-gray-900 transition-colors"
                >
                  <ChevronRight className="w-5 h-5 rotate-180" />
                  <span className="font-medium">Back to Agents</span>
                </button>
              </div>
            )}

            {/* Detail Form */}
            <div className="flex-1 overflow-y-auto px-4 lg:px-6 py-4 lg:py-6 space-y-4 lg:space-y-6 scrollbar-hide">
                {/* Basic Info */}
                <Card>
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
                    <div className="flex items-center gap-2">
                      <User className="w-5 h-5 text-gray-600" />
                      <h3 className="text-lg font-semibold text-gray-900">Basic Information</h3>
                    </div>
                    <div className="flex gap-2 lg:gap-3">
                      <Button
                        variant="primary"
                        icon={<Save className="w-4 h-4" />}
                        onClick={handleSave}
                        size="sm"
                      >
                        Save
                      </Button>
                      {!isCreating && selectedCharacter && (
                        <Button
                          variant="danger"
                          icon={<Trash2 className="w-4 h-4" />}
                          onClick={() => handleDelete(selectedCharacter.id)}
                          size="sm"
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="space-y-4">
                    {/* Avatar and Name/Description row */}
                    <div className="flex flex-col lg:flex-row gap-4">
                      {/* Left: Avatar - using flex to match height */}
                      <div className="flex-shrink-0 relative self-stretch flex items-center justify-center lg:justify-start">
                        <div className="relative">
                          <Avatar seed={formData.avatar || formData.name} size={120} className="w-[120px] h-[120px] lg:w-[160px] lg:h-[160px]" color={formData.color} />
                          <button
                            onClick={handleRegenerateAvatar}
                            className="absolute top-2 right-2 w-8 h-8 bg-white border-2 border-gray-300 rounded-full flex items-center justify-center hover:bg-gray-50 hover:border-primary-500 transition-all shadow-md"
                            title="Regenerate avatar"
                          >
                            <RefreshCw className="w-4 h-4 text-gray-700" />
                          </button>
                        </div>
                      </div>

                      {/* Right: Name and Description */}
                      <div className="flex-1 flex flex-col justify-between">
                        <Input
                          label="Name"
                          value={formData.name}
                          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                          placeholder="Agent Name"
                          required
                        />

                        <div className="flex-1 flex flex-col">
                          <label className="block text-sm font-medium text-gray-700 mb-1.5">
                            Description <span className="text-red-500">*</span>
                          </label>
                          <textarea
                            value={formData.description}
                            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                            className="flex-1 w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                            placeholder="Brief description of the agent's role"
                          />
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        Default Model <span className="text-red-500">*</span>
                      </label>
                      <select
                        value={formData.default_model}
                        onChange={(e) => setFormData({ ...formData, default_model: e.target.value })}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      >
                        <option value="haiku">Haiku (Fast)</option>
                        <option value="sonnet">Sonnet (Balanced)</option>
                        <option value="opus">Opus (Powerful)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        Personality
                      </label>
                      <textarea
                        value={formData.personality}
                        onChange={(e) => setFormData({ ...formData, personality: e.target.value })}
                        rows={2}
                        placeholder="Optional personality description"
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                  </div>
                </Card>

                {/* Capabilities Card */}
                <Card>
                  <div className="flex items-center gap-2 mb-4">
                    <Cpu className="w-5 h-5 text-gray-600" />
                    <h3 className="text-lg font-semibold text-gray-900">Capabilities</h3>
                  </div>
                  <div className="space-y-6">
                    <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                      <p className="text-sm text-blue-900">
                        <strong>Note:</strong> Agent capabilities (tools, MCP servers, skills) are stored in the database.
                        The agent.md file contains only personality and system prompt content.
                      </p>
                    </div>

                    {/* MCP Servers Section */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Settings className="w-4 h-4 text-gray-600" />
                        <label className="block text-sm font-medium text-gray-700">
                          MCP Servers
                        </label>
                      </div>
                      <p className="text-xs text-gray-500 mb-3">
                        Select which MCP (Model Context Protocol) servers this agent can connect to. MCP servers provide additional tools and capabilities.
                      </p>
                      <McpServerSelector
                        availableServers={availableMcpServers}
                        selectedServerIds={selectedMcpServers}
                        onAddServer={addMcpServer}
                        onRemoveServer={removeMcpServer}
                        isEditing={true}
                      />
                    </div>

                    {/* Skills Section */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Package className="w-4 h-4 text-gray-600" />
                        <label className="block text-sm font-medium text-gray-700">
                          Skills
                        </label>
                      </div>
                      <p className="text-xs text-gray-500 mb-3">
                        Select which skills this agent has access to. Skills provide documentation and resources but do not declare tools.
                      </p>
                      <SkillSelector
                        availableSkills={availableSkills}
                        selectedSkillIds={selectedSkills}
                        onAddSkill={addSkill}
                        onRemoveSkill={removeSkill}
                        isEditing={true}
                      />
                    </div>
                  </div>
                </Card>

                {/* Files Card */}
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
                      {selectedFile && (() => {
                        // Don't show rename/delete for agent.md or skill directories/files
                        if (selectedFile === 'agent.md') return null;

                        const skillIds = selectedCharacter?.capabilities?.allowed_skills || [];
                        const isSkillPath = skillIds.some(skillId =>
                          selectedFile === skillId || selectedFile.startsWith(`${skillId}/`)
                        );

                        if (isSkillPath) return null;

                        return (
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
                        );
                      })()}
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
                        Enter file path (e.g., "docs/guide.md" or "resources/notes.txt")
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

                  <div className="flex flex-col lg:flex-row gap-4 h-auto lg:h-[700px]">
                    {/* File Tree */}
                    <div className="w-full lg:w-64 border-b lg:border-b-0 lg:border-r-2 border-primary-500 pb-4 lg:pb-0 lg:pr-4 overflow-y-auto scrollbar-hide max-h-60 lg:max-h-none">
                      {characterFiles.length > 0 ? (
                        <FileTree
                          nodes={characterFiles}
                          selectedFile={selectedFile}
                          expandedDirs={expandedDirs}
                          onFileSelect={(path) => handleFileSelect(selectedCharacter!.id, path)}
                          onToggleDir={toggleDirectory}
                        />
                      ) : (
                        <div className="text-center py-12 text-gray-400">
                          <Folder className="w-12 h-12 mx-auto mb-2 opacity-50" />
                          <p className="text-sm">No files yet</p>
                        </div>
                      )}
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
              <User className="w-8 h-8 mx-auto mb-4 text-gray-400" />
              <p className="text-lg font-medium text-gray-900">Select a character</p>
              <p className="text-sm text-gray-500 mt-1">or create a new one to get started</p>
            </div>
          </div>
        )}
      </div>

      {/* Character Assistant Chat Toggle Button */}
      {!isChatOpen && (
        <button
          onClick={() => {
            setIsChatOpen(true);
            localStorage.setItem('isCharacterChatOpen', JSON.stringify(true));
          }}
          className="fixed bottom-20 lg:bottom-6 right-6 w-14 h-14 bg-white border border-gray-200 hover:bg-gray-50 rounded-full shadow-md flex items-center justify-center transition-colors z-50"
          aria-label="Open character assistant chat"
          title="Talk to your Character Assistant"
        >
          <User className="w-6 h-6 text-gray-600" />
        </button>
      )}
    </div>
  );
}

// FileTree Component (same as in Skills)
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
