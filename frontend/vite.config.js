import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'path'

export default defineConfig({
  // Production assets are committed and served as-is; ship without source maps to keep the bundle
  // lean and avoid exposing source. (frappe-ui's plugin owns build.sourcemap, so set it here.)
  // indexHtmlPath is set explicitly: frappe-ui otherwise infers it by walking up to a bench
  // `apps/` folder, which fails in CI where the app is checked out standalone (build then throws
  // "indexHtmlPath is required"). Pinning it makes the build work in and out of a bench.
  plugins: [frappeui({ frontendRoute: '/forms', buildConfig: { sourcemap: false, indexHtmlPath: '../forms/www/forms.html' } }), vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  build: {
    target: 'es2015',
  },
})
