import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // API 서버(Spring Boot, :8081)로 프록시
    proxy: { '/api': 'http://localhost:8081' },
  },
})
