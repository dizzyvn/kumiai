import { useState, useMemo, useCallback } from 'react';
import { Plus, X } from 'lucide-react';
import { Input } from './ui/Input';
import { getSkillIcon } from '../constants/skillIcons';
import { LAYOUT, EMPTY_STATE_MESSAGE } from '../constants/ui';
import type { Skill } from '../types/skill';

// Local constants
const SKILL_LIST_HEIGHT = LAYOUT.SKILL_LIST_HEIGHT;

interface SkillSelectorProps {
  availableSkills: Skill[];
  selectedSkillIds: string[];
  onAddSkill: (skillId: string) => void;
  onRemoveSkill: (skillId: string) => void;
  isEditing: boolean;
}

// Extracted Components
interface SkillCardProps {
  skill: Skill;
  onRemove?: (skillId: string) => void;
  showRemoveButton?: boolean;
}

function SkillCard({ skill, onRemove, showRemoveButton = true }: SkillCardProps) {
  const IconComponent = getSkillIcon(skill.icon);

  return (
    <button
      type="button"
      onClick={() => onRemove?.(skill.id)}
      className={`relative w-20 h-20 border border-gray-300 hover:border-red-300 transition-all flex items-center justify-center cursor-pointer rounded-lg group ${skill.iconColor ? '' : 'bg-white'}`}
      style={skill.iconColor ? { backgroundColor: skill.iconColor } : undefined}
      title={`${skill.name} (click to remove)`}
      aria-label={`Remove ${skill.name}`}
    >
      <IconComponent className="w-6 h-6 text-white group-hover:text-red-600 transition-colors" />
    </button>
  );
}

interface AvailableSkillCardProps {
  skill: Skill;
  onAdd: (skillId: string) => void;
}

function AvailableSkillCard({ skill, onAdd }: AvailableSkillCardProps) {
  const IconComponent = getSkillIcon(skill.icon);

  return (
    <button
      type="button"
      onClick={() => onAdd(skill.id)}
      className="w-full px-3 py-3 rounded-lg border border-gray-200 bg-white hover:border-primary-300 hover:bg-primary-50 transition-all text-left"
      aria-label={`Add ${skill.name}`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${skill.iconColor ? '' : 'bg-gray-100'}`}
          style={skill.iconColor ? { backgroundColor: skill.iconColor } : undefined}
        >
          <IconComponent className="w-6 h-6 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-gray-900 text-sm mb-1">
            {skill.name}
          </div>
          <div className="text-xs text-gray-600 line-clamp-2">
            {skill.description}
          </div>
        </div>
        <div className="flex-shrink-0 opacity-60">
          <Plus className="w-4 h-4 text-primary-600" />
        </div>
      </div>
    </button>
  );
}

interface EmptyStateProps {
  message: string;
}

function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="text-sm text-gray-500 text-center py-8">
      {message}
    </div>
  );
}

// Main Component
export function SkillSelector({
  availableSkills,
  selectedSkillIds,
  onAddSkill,
  onRemoveSkill,
  isEditing,
}: SkillSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('');

  // Memoized computations
  const validSkills = useMemo(
    () => selectedSkillIds
      .map((skillId) => availableSkills.find((s) => s.id === skillId))
      .filter((skill): skill is Skill => skill !== undefined),
    [selectedSkillIds, availableSkills]
  );

  const unselectedSkills = useMemo(
    () => availableSkills.filter((skill) => !selectedSkillIds.includes(skill.id)),
    [availableSkills, selectedSkillIds]
  );

  const filteredAvailableSkills = useMemo(() => {
    if (!searchQuery) return unselectedSkills;
    const query = searchQuery.toLowerCase();
    return unselectedSkills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query)
    );
  }, [unselectedSkills, searchQuery]);

  // Memoized callbacks
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value),
    []
  );

  // Render helpers
  const renderSkillsList = useCallback(
    (skills: Skill[]) => {
      const gridSize = 9; // 3x3 grid

      if (skills.length === 0) {
        // Show all empty cells when no skills
        return Array.from({ length: gridSize }).map((_, idx) => (
          <div
            key={`empty-${idx}`}
            className="w-20 h-20 border border-gray-300 bg-gray-100 rounded-lg"
          />
        ));
      }

      // Render skills + empty cells to fill the grid
      const cells = skills.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          onRemove={onRemoveSkill}
          showRemoveButton
        />
      ));

      // Add empty cells to fill remaining grid spaces
      const emptyCellsCount = gridSize - (skills.length % gridSize);
      if (emptyCellsCount < gridSize) {
        for (let i = 0; i < emptyCellsCount; i++) {
          cells.push(
            <div
              key={`empty-${i}`}
              className="w-20 h-20 border border-gray-300 bg-gray-100 rounded-lg"
            />
          );
        }
      }

      return cells;
    },
    [onRemoveSkill]
  );

  const renderAvailableSkills = useCallback(() => {
    if (filteredAvailableSkills.length === 0) {
      const message = searchQuery
        ? EMPTY_STATE_MESSAGE.NO_RESULTS
        : EMPTY_STATE_MESSAGE.ALL_ADDED;
      return <EmptyState message={message} />;
    }

    return filteredAvailableSkills.map((skill) => (
      <AvailableSkillCard key={skill.id} skill={skill} onAdd={onAddSkill} />
    ));
  }, [filteredAvailableSkills, searchQuery, onAddSkill]);

  // Common selected skills panel
  const selectedSkillsPanel = (
    <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${SKILL_LIST_HEIGHT} flex items-center justify-center`}>
      <div className="grid grid-cols-3 gap-2 w-fit">
        {renderSkillsList(validSkills)}
      </div>
    </div>
  );

  // Read-only view
  if (!isEditing) {
    return (
      <div className="flex flex-col lg:flex-row gap-3">
        {selectedSkillsPanel}
      </div>
    );
  }

  // Edit mode view
  return (
    <div className="flex flex-col lg:flex-row gap-3">
      {selectedSkillsPanel}

      {/* Available Skills Panel */}
      <div className={`border border-gray-200 rounded-lg p-4 bg-gray-50 ${SKILL_LIST_HEIGHT} flex flex-col flex-1`}>
        <Input
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder="Search skills to add"
          className="mb-2.5 flex-shrink-0"
          aria-label="Search available skills"
        />

        <div className="space-y-2 flex-1 overflow-y-auto scrollbar-hide">
          {renderAvailableSkills()}
        </div>
      </div>
    </div>
  );
}
