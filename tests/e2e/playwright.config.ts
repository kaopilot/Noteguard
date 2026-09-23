// I1 E2E smoke config (owner I1). Driven by tests/e2e/test_e2e_smoke.py; run from frontend/ with NODE_PATH=frontend/node_modules.
// Starts the REAL app (noteguard.api.app:app = real engine + approval gate) and the BUILT frontend; never reuses a running server.
import { defineConfig } from '@playwright/test';

const executablePath = process.env.NG_CHROMIUM;

export default defineConfig({
  testDir: '.',
  testMatch: 'smoke.spec.ts',
  timeout: 120_000,
  workers: 1,
  reporter: 'list',
  outputDir: '../../frontend/test-results/i1-smoke',
  use: { baseURL: 'http://127.0.0.1:4173', viewport: { width: 1440, height: 900 }, launchOptions: executablePath ? { executablePath } : {} },
  webServer: [
    { command: 'uv run uvicorn noteguard.api.app:app --host 127.0.0.1 --port 8000', cwd: '../..', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false },
    { command: 'npm run build && npm run preview', cwd: '../../frontend', url: 'http://127.0.0.1:4173', reuseExistingServer: false, timeout: 120_000 },
  ],
});
