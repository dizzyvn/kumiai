/**
 * Frontend configuration with environment variable support
 */

const getApiUrl = () => {
  // Check if we have an environment variable
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // Use configurable port from environment or default
  const port = import.meta.env.VITE_API_PORT || '7892';

  // If running in browser, use current hostname
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    return `http://${hostname}:${port}`;
  }

  // Fallback to localhost
  return `http://localhost:${port}`;
};

export const config = {
  // API configuration
  apiUrl: getApiUrl(),

  // Path configuration
  // Note: These are server-side paths passed to the backend API
  // The backend will resolve them relative to its base directory
  paths: {
    // Use env vars if provided, otherwise use relative paths that the backend will resolve
    projectRoot: import.meta.env.VITE_PROJECT_ROOT || './poc-multiagent',
    skillLibrary: import.meta.env.VITE_SKILL_LIBRARY_PATH || './poc-multiagent/skill_library',
    characterLibrary: import.meta.env.VITE_CHARACTER_LIBRARY_PATH || './poc-multiagent/character_library',
  },
};

// Export individual values for convenience
export const { apiUrl, paths } = config;
