import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// AgentForge 前端构建配置：
// - base 与 outDir 对齐 FastAPI 的 StaticFiles 挂载（/static → interfaces/static）
// - 构建产物输出至 interfaces/static/spa，作为交付产物保留
export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../static/spa',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/stream': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      // 开发模式下本地字体同样经由后端 /static 挂载提供
      '/static/fonts': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
