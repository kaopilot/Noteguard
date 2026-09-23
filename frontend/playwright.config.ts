// Real-browser walk of the B3 main path (not part of `make test`: it needs a browser and two servers).
// Run: npm run e2e  (set NG_CHROMIUM to a local Chromium binary if Playwright's own is not installed).
import { defineConfig } from '@playwright/test';

const executablePath = process.env.NG_CHROMIUM;

export default defineConfig({
  testDir: 'e2e',
  timeout: 90_000,
  workers: 1,
  reporter: 'list',
  outputDir: 'test-results',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    launchOptions: executablePath ? { executablePath } : {},
    serviceWorkers: 'allow',
  },
  projects: [
    { name: 'mobile-375', use: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    { command: 'uv run uvicorn noteguard.api.app:app --host 127.0.0.1 --port 8000', cwd: '..', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: true },
    { command: 'npm run build && npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true, timeout: 120_000 },
  ],
});
