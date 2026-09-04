import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is proxied so the app talks to a same-origin /api in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
