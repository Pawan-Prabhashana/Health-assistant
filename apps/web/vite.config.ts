/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// During local development the dev server proxies API calls to the FastAPI
// backend so the browser always talks to a single origin, matching the nginx
// reverse-proxy behaviour used in the container topology. The `test` block
// configures Vitest (jsdom, RTL) so component and hook tests run without a
// backend against MSW-mocked endpoints.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/api/schema.d.ts', 'src/test/**', 'src/main.tsx'],
    },
  },
});
