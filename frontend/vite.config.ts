import { defineConfig } from 'vite'

export default defineConfig({
  esbuild: { jsx: 'automatic', jsxImportSource: 'react' },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
