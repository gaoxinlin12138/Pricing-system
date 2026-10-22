import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/uploads': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
    },
    watch: {
      // 编辑器保存时会在源码目录生成临时文件/目录；不忽略时 Windows 上的 watcher 会报 EBUSY 并退出。
      ignored: ['**/.*.tmpdir/**', '**/.*.tmp', '**/.*.tmpdir'],
    },
  },
})
