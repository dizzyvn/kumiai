import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0', // Listen on all network interfaces
    port: 1420,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:7892',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
},
});
