import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:5004',
      '/design': 'http://localhost:5004',
      '/canvas': 'http://localhost:5004',
      '/settings': 'http://localhost:5004',
      '/audit': 'http://localhost:5004'
    }
  }
})
