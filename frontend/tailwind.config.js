/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
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
        success: '#65b52a',  // Bright green
        warning: '#e03a46',  // Red
        error: '#e03a46',    // Red
        info: '#253779',     // Deep blue
      },
      fontFamily: {
        serif: ['Georgia', 'serif'],
        sans: ['Noto Sans Display', 'Noto Emoji', 'sans-serif'],
        mono: ['Consolas', 'Monaco', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [
    function({ addUtilities }) {
      addUtilities({
        '.scrollbar-hide': {
          /* Firefox */
          'scrollbar-width': 'none',
          /* Safari and Chrome */
          '&::-webkit-scrollbar': {
            display: 'none'
          }
        }
      })
    }
  ],
}
