import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import path from 'path';

// Dev-only design lab (#462): its own entry (lab.html -> src/lab/main.jsx) and
// out dir, never part of the main (dist/) or demo (dist-demo/) bundles. It needs
// no API, so there is no proxy. `npm run lab` serves it at
// http://127.0.0.1:5182/lab.html; `npm run build:lab` + `npm run preview:lab`
// serve a production build of it at http://127.0.0.1:4175/lab.html.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist-lab',
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'lab.html'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5182,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 4175,
    strictPort: true,
  },
});
