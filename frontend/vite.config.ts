import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['tvs_logo.png', 'tvs_logo_192.png', 'tvs_logo_512.png'],
      manifest: {
        name: 'Coop Vision',
        short_name: 'Coop Vision',
        description: 'Multi-farm, multi-user poultry monitoring system',
        id: '/?source=pwa',
        theme_color: '#0f172a',
        background_color: '#f8fafc',
        display: 'standalone',
        display_override: ['standalone', 'window-controls-overlay'],
        orientation: 'portrait-primary',
        start_url: '/',
        dir: 'ltr',
        categories: ['business', 'utilities'],
        prefer_related_applications: false,
        related_applications: [],
        launch_handler: {
          client_mode: ['navigate-existing', 'auto']
        },
        icons: [
          {
            src: 'tvs_logo_192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'tvs_logo_512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'tvs_logo_192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable'
          },
          {
            src: 'tvs_logo_512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable'
          }
        ],
        screenshots: [
          {
            src: 'dashboard_screenshot.png',
            sizes: '1920x945',
            type: 'image/png',
            form_factor: 'wide',
            label: 'Coop Vision Dashboard'
          },
          {
            src: 'login_screenshot.png',
            sizes: '1920x945',
            type: 'image/png',
            form_factor: 'narrow',
            label: 'Coop Vision Login Page'
          }
        ],
        shortcuts: [
          {
            name: 'Overview',
            url: '/',
            icons: [{ src: 'tvs_logo_192.png', sizes: '192x192', type: 'image/png' }]
          },
          {
            name: 'Live Feed',
            url: '/live',
            icons: [{ src: 'tvs_logo_192.png', sizes: '192x192', type: 'image/png' }]
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        globIgnores: ['**/node_modules/**/*', '**/*.mp4'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'google-fonts-stylesheets',
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-webfonts',
              expiration: {
                maxEntries: 30,
                maxAgeSeconds: 60 * 60 * 24 * 365,
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
        ],
      },
    })
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
      '/hls': {
        target: 'http://127.0.0.1:8888',
        changeOrigin: true,
      },
    },
  },
})
