import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Dev: the backend runs on :8000; proxy REST, SSE and the voice WebSocket so the app is same-origin.
const backend = process.env.VITE_BACKEND ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
  server: {
    port: 5173,
    proxy: {
      '/api/voice/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
      '/api': { target: backend, changeOrigin: true },
      '/healthz': { target: backend, changeOrigin: true },
    },
  },
})
