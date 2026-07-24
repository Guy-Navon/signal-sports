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
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/react-router') ||
            id.includes('@tanstack/react-query')
          ) return 'react-vendor';
          if (id.includes('framer-motion')) return 'motion-vendor';
          if (id.includes('lucide-react')) return 'icons-vendor';
          if (id.includes('@radix-ui')) return 'ui-vendor';
          if (id.includes('date-fns')) return 'date-vendor';
          return undefined;
        },
      },
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
  },
});
