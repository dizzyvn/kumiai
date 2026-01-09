/**
 * Design System - Unified styling for the Multi-Agent System
 * Inspired by: Anthropic, OpenAI, Google, Apple
 *
 * Philosophy: Clean, Minimal, Functional
 */

// ============================================================================
// COLOR PALETTE
// ============================================================================

export const colors = {
  // Primary - Deep Blue (Main brand color)
  primary: {
    50: '#eff2fb',
    100: '#dfe5f7',
    200: '#bfcbef',
    300: '#9fb1e7',
    400: '#5f83d7',
    500: '#253779',  // Deep blue
    600: '#1e2c61',
    700: '#162149',
    800: '#0f1631',
    900: '#070b18',
  },

  // Secondary - Red
  secondary: {
    50: '#fcecee',
    100: '#f9d9dc',
    200: '#f3b3b9',
    300: '#ed8d96',
    400: '#e76773',
    500: '#e03a46',  // Red
    600: '#b32f38',
    700: '#86232a',
    800: '#5a181c',
    900: '#2d0c0e',
  },

  // Neutral - Gray scale
  gray: {
    50: '#ffffff',   // Pure white
    100: '#f9f9f9',
    200: '#e5e5e6',  // Light gray
    300: '#cccccd',
    400: '#b2b2b4',
    500: '#99999b',
    600: '#7a7a7c',
    700: '#5c5c5d',
    800: '#3d3d3e',
    900: '#161938',  // Dark navy
  },

  // Accent - Bright Green
  accent: {
    50: '#f2fbed',
    100: '#e5f7db',
    200: '#cbefb7',
    300: '#b1e793',
    400: '#97df6f',
    500: '#65b52a',  // Bright green
    600: '#519122',
    700: '#3d6d19',
    800: '#284811',
    900: '#142408',
  },

  // Semantic colors
  success: '#65b52a',  // Bright green
  warning: '#e03a46',  // Red
  error: '#e03a46',    // Red
  info: '#253779',     // Deep blue

  // Background
  background: '#ffffff',        // Pure white
  backgroundSecondary: '#f9f9f9',

  // Surface
  surface: '#ffffff',
  surfaceHover: '#f9f9f9',

  // Border
  border: '#e5e5e6',
  borderHover: '#cccccd',

  // Text
  text: {
    primary: '#161938',    // Dark navy
    secondary: '#5c5c5d',
    tertiary: '#99999b',
    inverse: '#ffffff',    // Pure white
  },
};

// ============================================================================
// TYPOGRAPHY
// ============================================================================

export const typography = {
  fontFamily: {
    sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    mono: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
  },

  fontSize: {
    xs: '0.75rem',      // 12px
    sm: '0.875rem',     // 14px
    base: '1rem',       // 16px
    lg: '1.125rem',     // 18px
    xl: '1.25rem',      // 20px
    '2xl': '1.5rem',    // 24px
    '3xl': '1.875rem',  // 30px
    '4xl': '2.25rem',   // 36px
  },

  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },

  lineHeight: {
    tight: '1.25',
    normal: '1.5',
    relaxed: '1.75',
  },
};

// ============================================================================
// SPACING
// ============================================================================

export const spacing = {
  0: '0',
  1: '0.25rem',   // 4px
  2: '0.5rem',    // 8px
  3: '0.75rem',   // 12px
  4: '1rem',      // 16px
  5: '1.25rem',   // 20px
  6: '1.5rem',    // 24px
  8: '2rem',      // 32px
  10: '2.5rem',   // 40px
  12: '3rem',     // 48px
  16: '4rem',     // 64px
  20: '5rem',     // 80px
  24: '6rem',     // 96px
};

// ============================================================================
// BORDER RADIUS
// ============================================================================

export const radius = {
  none: '0',
  sm: '0.25rem',    // 4px
  base: '0.5rem',   // 8px
  md: '0.75rem',    // 12px
  lg: '1rem',       // 16px
  xl: '1.5rem',     // 24px
  full: '9999px',
};

// ============================================================================
// BORDER WIDTH
// ============================================================================

export const borderWidth = {
  0: '0',
  1: '1px',
  2: '2px',
  4: '4px',
  8: '8px',
  default: '1px',
};

// ============================================================================
// SHADOWS
// ============================================================================

export const shadows = {
  none: 'none',
  sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
  base: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
  md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
};

// ============================================================================
// TRANSITIONS
// ============================================================================

export const transitions = {
  fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
  base: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
  slow: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
};

// ============================================================================
// LAYOUT
// ============================================================================

export const breakpoints = {
  sm: 640,   // Small devices (mobile landscape)
  md: 768,   // Medium devices (tablets)
  lg: 1024,  // Large devices (desktop)
  xl: 1280,  // Extra large devices
  '2xl': 1536, // 2X Extra large devices
};

export const layout = {
  // Sidebar widths (responsive)
  sidebar: {
    desktop: '20%',      // >= lg breakpoint
    tablet: '30%',       // md to lg
    mobile: '100%',      // < md (overlay mode)
  },

  // PM Chat panel
  pmChat: {
    desktop: '400px',    // >= lg breakpoint
    mobile: '100%',      // < lg (full-screen overlay)
  },

  // Mobile-specific
  mobile: {
    bottomNavHeight: '64px',
    headerHeight: '56px',
    touchTarget: '44px',  // Minimum touch target size
    drawerMaxWidth: '85vw', // Mobile drawer max width
  },

  // Desktop-specific
  desktop: {
    headerHeight: '64px',
    sidebarMinWidth: '240px',
    sidebarMaxWidth: '400px',
  },

  // Legacy (for backward compatibility during migration)
  sidebarWidth: '20%',
};

// ============================================================================
// COMPONENT STYLES (Class Names)
// ============================================================================

export const components = {
  // Buttons
  button: {
    base: 'inline-flex items-center justify-center font-medium transition-all rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2',

    variants: {
      primary: 'bg-white border-2 border-primary-600 text-primary-600 hover:bg-primary-50 focus:ring-primary-500',
      secondary: 'bg-white border-2 border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500',
      outline: 'border-2 border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus:ring-gray-500',
      ghost: 'text-gray-700 hover:bg-gray-100 focus:ring-gray-500',
      danger: 'bg-white border-2 border-red-600 text-red-600 hover:bg-red-50 focus:ring-red-500',
    },

    sizes: {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2 text-base',
      lg: 'px-6 py-3 text-lg',
    },
  },

  // Input fields
  input: {
    base: 'w-full rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
    default: 'bg-white border-gray-300 text-gray-900 placeholder-gray-400',
    disabled: 'bg-gray-50 border-gray-200 text-gray-500 cursor-not-allowed',

    sizes: {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2 text-base',
      lg: 'px-4 py-3 text-lg',
    },
  },

  // Cards
  card: {
    base: 'bg-white rounded-lg border border-gray-200',
    hover: 'hover:border-gray-300 hover:shadow-sm transition-all',
    interactive: 'cursor-pointer hover:border-gray-300 hover:shadow-md transition-all',
    padding: {
      sm: 'p-4',
      md: 'p-6',
      lg: 'p-8',
    },
  },

  // Navigation
  nav: {
    item: {
      base: 'flex items-center gap-2 px-3 py-2 font-medium transition-all',
      active: 'bg-primary-50 text-primary-700',
      inactive: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
    },
  },

  // Headers
  header: {
    page: 'bg-white border-b border-gray-200 px-6 py-4',
    title: 'text-2xl font-semibold text-gray-900',
    subtitle: 'text-sm text-gray-600 mt-1',
  },

  // Badges/Tags
  badge: {
    base: 'inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium',
    variants: {
      primary: 'bg-primary-50 text-primary-700',
      secondary: 'bg-gray-100 text-gray-700',
      success: 'bg-green-50 text-green-700',
      warning: 'bg-yellow-50 text-yellow-700',
      error: 'bg-red-50 text-red-700',
    },
  },

  // List items
  listItem: {
    base: 'p-4 cursor-pointer transition-all',
    hover: 'hover:bg-gray-50',
    selected: 'bg-primary-50 border-l-4 border-primary-600',
    divider: 'border-b border-gray-200',
  },
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

export const cn = (...classes: (string | undefined | null | false)[]) => {
  return classes.filter(Boolean).join(' ');
};

export const getButtonClass = (
  variant: keyof typeof components.button.variants = 'primary',
  size: keyof typeof components.button.sizes = 'md'
) => {
  return cn(
    components.button.base,
    components.button.variants[variant],
    components.button.sizes[size]
  );
};

export const getInputClass = (
  size: keyof typeof components.input.sizes = 'md',
  disabled = false
) => {
  return cn(
    components.input.base,
    disabled ? components.input.disabled : components.input.default,
    components.input.sizes[size]
  );
};

export const getCardClass = (interactive = false, padding: keyof typeof components.card.padding = 'md') => {
  return cn(
    components.card.base,
    interactive ? components.card.interactive : components.card.hover,
    components.card.padding[padding]
  );
};
