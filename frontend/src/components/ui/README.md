# UI Components Library

Reusable components following the opcode design system with the new color palette.

## Design System

All components use the centralized design system from `@/styles/design-system.ts`:

- **Colors**: Red Damask primary (#d65c4f), Carrara background (#F4F3F0), Abbey text (#474b4e)
- **Border Width**: Standardized values (1px, 2px, 4px, 8px)
- **Spacing**: Consistent padding and margins
- **Typography**: Noto Sans Display for UI text

---

## Layout Components

### Sidebar

A complete sidebar component with search, content area, and bottom actions.

**Usage:**
```tsx
import { Sidebar } from '@/components/ui';
import { Folder, Plus } from 'lucide-react';

<Sidebar
  // Search
  searchValue={searchQuery}
  onSearchChange={setSearchQuery}
  searchPlaceholder="Search projects..."

  // Empty state
  isLoading={loading}
  isEmpty={projects.length === 0}
  emptyIcon={Folder}
  emptyTitle="No projects yet"
  emptyDescription="Create one to get started"

  // Bottom actions
  primaryAction={{
    label: 'New Project',
    icon: <Plus className="w-5 h-5" />,
    onClick: handleCreate
  }}
  secondaryActions={[
    {
      label: 'Import',
      icon: <Download className="w-5 h-5" />,
      onClick: handleImport,
      variant: 'secondary'
    }
  ]}
>
  {/* Your list items here */}
  {projects.map(project => (
    <ProjectCard key={project.id} project={project} />
  ))}
</Sidebar>
```

**Props:**
- `searchValue?: string` - Search input value
- `onSearchChange?: (value: string) => void` - Search change handler
- `searchPlaceholder?: string` - Search input placeholder
- `showSearch?: boolean` - Show/hide search bar (default: true)
- `children: React.ReactNode` - Main content area
- `isLoading?: boolean` - Show loading state
- `isEmpty?: boolean` - Show empty state
- `emptyIcon?: LucideIcon` - Icon for empty state
- `emptyTitle?: string` - Empty state title
- `emptyDescription?: string` - Empty state description
- `primaryAction?: ActionButton` - Main action button
- `secondaryActions?: ActionButton[]` - Additional action buttons
- `bottomContent?: React.ReactNode` - Custom bottom content
- `width?: string` - Sidebar width (default: from design system)

---

### BottomActionBar

Fixed bottom container for action buttons.

**Usage:**
```tsx
import { BottomActionBar } from '@/components/ui';
import { Plus, Download } from 'lucide-react';

<BottomActionBar
  primaryAction={{
    label: 'New Item',
    icon: <Plus className="w-5 h-5" />,
    onClick: handleCreate
  }}
  secondaryActions={[
    {
      label: 'Import',
      icon: <Download className="w-5 h-5" />,
      onClick: handleImport,
      variant: 'secondary'
    }
  ]}
  customContent={
    <label className="flex items-center gap-2 text-xs text-gray-600">
      <input type="checkbox" checked={showArchived} />
      Show archived
    </label>
  }
/>
```

**Props:**
- `primaryAction: ActionButton` - Main action button (required)
- `secondaryActions?: ActionButton[]` - Additional buttons
- `customContent?: React.ReactNode` - Custom content (e.g., checkboxes)

**ActionButton interface:**
```typescript
{
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  disabled?: boolean;
}
```

---

## Content Components

### SearchBar

Consistent search input with icon.

**Usage:**
```tsx
import { SearchBar } from '@/components/ui';

<SearchBar
  value={searchQuery}
  onChange={setSearchQuery}
  placeholder="Search items..."
/>
```

**Props:**
- `value: string` - Input value
- `onChange: (value: string) => void` - Change handler
- `placeholder?: string` - Placeholder text
- `className?: string` - Additional CSS classes

---

### EmptyState

Placeholder for empty or loading states.

**Usage:**
```tsx
import { EmptyState } from '@/components/ui';
import { Folder } from 'lucide-react';

// Loading state
<EmptyState
  icon={Folder}
  title="Loading projects..."
  isLoading={true}
/>

// Empty state
<EmptyState
  icon={Folder}
  title="No projects found"
  description="Try a different search term or create a new project"
/>
```

**Props:**
- `icon: LucideIcon` - Icon component (from lucide-react)
- `title: string` - Main message
- `description?: string` - Secondary message
- `isLoading?: boolean` - Show pulse animation
- `className?: string` - Additional CSS classes

---

### SectionHeader

Header for detail panel sections with icon, title, and actions.

**Usage:**
```tsx
import { SectionHeader } from '@/components/ui';
import { User, Edit, Save, X } from 'lucide-react';

<SectionHeader
  icon={User}
  title="Basic Information"
  subtitle="Configure your agent's identity"
  actions={[
    {
      label: 'Edit',
      icon: <Edit className="w-4 h-4" />,
      onClick: handleEdit,
      variant: 'secondary'
    },
    {
      label: 'Save',
      icon: <Save className="w-4 h-4" />,
      onClick: handleSave,
      variant: 'primary'
    }
  ]}
/>
```

**Props:**
- `icon: LucideIcon` - Section icon
- `title: string` - Section title
- `subtitle?: string` - Optional subtitle
- `actions?: SectionAction[]` - Action buttons
- `className?: string` - Additional CSS classes

**SectionAction interface:**
```typescript
{
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}
```

---

## Form Components

### Button

Standard button component (already exists).

**Usage:**
```tsx
import { Button } from '@/components/ui';
import { Plus } from 'lucide-react';

<Button
  variant="primary"
  size="md"
  icon={<Plus className="w-5 h-5" />}
  onClick={handleClick}
>
  Create New
</Button>
```

---

### Input

Standard input component (already exists).

**Usage:**
```tsx
import { Input } from '@/components/ui';

<Input
  value={name}
  onChange={(e) => setName(e.target.value)}
  placeholder="Enter name..."
/>
```

---

### Card

Container component for sections (already exists).

**Usage:**
```tsx
import { Card } from '@/components/ui';

<Card>
  <h3>Card Title</h3>
  <p>Card content...</p>
</Card>
```

---

## Migration Guide

### Before (Projects.tsx example):

```tsx
{/* Old implementation - repetitive code */}
<div className="border-r border-gray-200 flex flex-col relative" style={{ width: layout.sidebarWidth }}>
  {/* Search */}
  <div className="flex-shrink-0 p-4 bg-white">
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search projects..."
        className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
      />
    </div>
  </div>

  {/* List */}
  <div className="flex-1 overflow-y-auto p-2">
    {loading && (
      <div className="p-6 text-center text-gray-500">
        <Folder className="w-12 h-12 mx-auto mb-2.5 text-gray-400 animate-pulse" />
        <p className="text-sm">Loading projects...</p>
      </div>
    )}
    {!loading && projects.length === 0 && (
      <div className="p-6 text-center text-gray-500">
        <Folder className="w-12 h-12 mx-auto mb-2.5 text-gray-400" />
        <p className="text-sm">No projects yet</p>
        <p className="text-xs text-gray-400 mt-1">Create one to get started</p>
      </div>
    )}
    {projects.map(project => (
      <ProjectCard key={project.id} project={project} />
    ))}
  </div>

  {/* Bottom Actions */}
  <div className="flex-shrink-0 border-t border-gray-200 bg-white p-4 space-y-3">
    <Button
      variant="primary"
      size="md"
      icon={<Plus className="w-5 h-5" />}
      onClick={() => setIsCreating(true)}
      className="w-full"
    >
      New Project
    </Button>
  </div>
</div>
```

### After (using Sidebar component):

```tsx
import { Sidebar } from '@/components/ui';
import { Folder, Plus } from 'lucide-react';

<Sidebar
  searchValue={searchQuery}
  onSearchChange={setSearchQuery}
  searchPlaceholder="Search projects..."
  isLoading={loading}
  isEmpty={projects.length === 0}
  emptyIcon={Folder}
  emptyTitle={searchQuery ? 'No projects found' : 'No projects yet'}
  emptyDescription={searchQuery ? 'Try a different search term' : 'Create one to get started'}
  primaryAction={{
    label: 'New Project',
    icon: <Plus className="w-5 h-5" />,
    onClick: () => setIsCreating(true)
  }}
>
  {projects.map(project => (
    <ProjectCard key={project.id} project={project} />
  ))}
</Sidebar>
```

**Benefits:**
- ✅ 80+ lines reduced to ~20 lines
- ✅ Consistent styling across all pages
- ✅ Easier to maintain and update
- ✅ Type-safe with TypeScript
- ✅ All design system values centralized

---

## Design System Integration

All components automatically use:

- **Primary color**: `primary-500` (#d65c4f - Red Damask)
- **Border color**: `gray-200`
- **Text colors**: `gray-900`, `gray-700`, `gray-500`
- **Background**: `white`, `gray-50`
- **Border radius**: `rounded-lg` (8px)
- **Focus ring**: `ring-primary-500`
- **Transitions**: `transition-colors`, `transition-all`

To update the design system globally, edit `/src/styles/design-system.ts`.

---

## Contributing

When creating new reusable components:

1. Place in `/src/components/ui/`
2. Export from `/src/components/ui/index.ts`
3. Document in this README
4. Use design system tokens from `@/styles/design-system`
5. Follow existing naming conventions
6. Include TypeScript interfaces for all props
