/**
 * Skill type definitions
 *
 * Skills are pure documentation - no tool/MCP server declarations.
 * Tool and MCP server requirements are in Character database.
 */

export interface Skill {
  id: string;
  name: string;
  description: string;
  icon?: string;
  iconColor?: string; // Background color for the icon
}

export interface SkillMetadata extends Skill {
  has_scripts?: boolean;
  has_resources?: boolean;
}

export interface SkillDefinition extends SkillMetadata {
  content: string;
  license: string;
  version: string;
}
