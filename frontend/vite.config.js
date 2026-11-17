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
    // SIGNAL_API_PROXY lets scripts/preview.ps1 run a second copy next to the live
    // stack (its own API port); unset, the proxy targets the live API as before.
    // xfwd appends X-Forwarded-For so the API's per-client login limiter sees the
    // real client, not this proxy (AUDIT_REPORT H1). uvicorn trusts the header only
    // from 127.0.0.1 and reads it right to left, so a client cannot forge its address.
    proxy: {
      '/api': { target: process.env.SIGNAL_API_PROXY || 'http://127.0.0.1:8000', xfwd: true },
      '/health': process.env.SIGNAL_API_PROXY || 'http://127.0.0.1:8000',
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
    // Several suites `await import()` the app's module graph inside the first
    // test (after vi.resetModules, so the env stub takes effect). That cold
    // transform is paid by whichever test runs first: ~2 s on an idle 4-core
    // machine, measured 4.0–4.8 s with three suites running at once — right at
    // Vitest's 5 s default, so a busy CI runner or a parallel local run could
    // fail a test that is functionally green. The ceiling only bounds hangs; it
    // changes no assertion, and genuinely stuck tests still fail.
    testTimeout: 20_000,
    hookTimeout: 20_000,
  },
});
