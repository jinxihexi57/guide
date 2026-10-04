import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@ant-design/icons-vue/es/icons/UpOutlined': resolve(
        __dirname,
        'node_modules/@ant-design/icons-vue/es/icons/ArrowUpOutlined.js'
      ),
      '@ant-design/icons-vue/es/icons/VerticalAlignTopOutlined': resolve(
        __dirname,
        'node_modules/@ant-design/icons-vue/es/icons/ArrowUpOutlined.js'
      ),
      '@ant-design/icons-vue/es/icons/WarningFilled': resolve(
        __dirname,
        'node_modules/@ant-design/icons-vue/es/icons/ExclamationCircleFilled.js'
      ),
      '@ant-design/icons-vue/es/icons/ZoomInOutlined': resolve(
        __dirname,
        'node_modules/@ant-design/icons-vue/es/icons/SearchOutlined.js'
      ),
      '@ant-design/icons-vue/es/icons/ZoomOutOutlined': resolve(
        __dirname,
        'node_modules/@ant-design/icons-vue/es/icons/SearchOutlined.js'
      )
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true
      }
    }
  }
})
