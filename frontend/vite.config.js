import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'path'

export default defineConfig({
  // Production assets are committed and served as-is; ship without source maps to keep the bundle
  // lean and avoid exposing source. (frappe-ui's plugin owns build.sourcemap, so set it here.)
  plugins: [frappeui({ frontendRoute: '/forms', buildConfig: { sourcemap: false } }), vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  build: {
    target: 'es2015',
  },
})
