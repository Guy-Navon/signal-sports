import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { readFile } from 'node:fs/promises';
import path from 'path';

// Dev-only design lab (#462): its own entry (lab.html -> src/lab/main.jsx) and
// out dir, never part of the main (dist/) or demo (dist-demo/) bundles. It needs
// no API, so there is no proxy. `npm run lab` serves it at
// http://127.0.0.1:5182/lab.html; `npm run build:lab` + `npm run preview:lab`
// serve a production build of it at http://127.0.0.1:4175/lab.html.
//
// The feed lab (lab.html?page=feed, #464) reads a real feed snapshot: the two
// files the public demo reads, served from SIGNAL_LAB_SNAPSHOT_DIR, or from
// dist-demo/demo-data (written by scripts/demo-publish.ps1). They are never
// copied into the repo or into any bundle.
const SNAPSHOT_FILES = new Set(['feed.json', 'meta.json']);

function labSnapshot() {
  const directory = path.resolve(
    __dirname,
    process.env.SIGNAL_LAB_SNAPSHOT_DIR || 'dist-demo/demo-data'
  );
  const serve = (server) => {
    server.middlewares.use('/demo-data', async (request, response, next) => {
      const name = (request.url || '').replace(/^\//, '').split('?')[0];
      if (!SNAPSHOT_FILES.has(name)) return next();
      try {
        const body = await readFile(path.join(directory, name));
        response.setHeader('Content-Type', 'application/json; charset=utf-8');
        response.setHeader('Cache-Control', 'no-store');
        response.end(body);
      } catch {
        response.statusCode = 404;
        response.end(`no ${name} in ${directory}`);
      }
    });
  };
  return { name: 'lab-snapshot', configureServer: serve, configurePreviewServer: serve };
}

export default defineConfig({
  plugins: [react(), labSnapshot()],
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
