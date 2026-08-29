import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Resolved from import.meta.url rather than node:path so this browser app never pulls
// Node type declarations into its program.
const srcDir = decodeURIComponent(new URL('./src', import.meta.url).pathname)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': srcDir,
    },
  },
  server: {
    // getUserMedia is only exposed in a secure context; localhost counts as one.
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
