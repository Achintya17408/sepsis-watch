import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_ACTIONS ? '/sepsis-watch/' : '/',
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* → FastAPI during local dev
      // (production uses VITE_API_URL env var in api.ts instead)
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
