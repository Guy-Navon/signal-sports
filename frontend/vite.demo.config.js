import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import path from 'path';

// The public read-only demo (#458): its own entry (demo.html → src/demo/main.jsx)
// and its own out dir: feed/results views with static details, no router, auth,
// app provider, preferences or ops pages. Firebase Hosting serves
// dist-demo/ (firebase.json at the repo root); scripts/demo-publish.ps1 writes
// the snapshot into dist-demo/demo-data/ before each deploy.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist-demo',
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'demo.html'),
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4174,
    strictPort: true,
  },
});
