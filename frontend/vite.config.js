import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true, // Tailscale Serve points at 5173; fail loudly instead of drifting to 5174
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'node',
    globals: true,
    // Neutralise the developer's gitignored .env.local. Without this the suite
    // inherits whatever VITE_DATA_MODE that file sets, so a test can pass on a
    // workstation and fail on a clean checkout — which is exactly how the
    // session-bootstrap tests reached CI green locally and red on GitHub.
    // Tests that need a mode declare it themselves via vi.stubEnv.
    env: { VITE_DATA_MODE: '' },
  },
});
