import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 5174,
      host: '0.0.0.0',
      allowedHosts: [
        'inarbit.work',
        'www.inarbit.work',
        '136.109.140.114',
        'localhost',
        '127.0.0.1'
      ]
    }
  }
})
