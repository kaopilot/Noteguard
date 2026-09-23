/// <reference types="vitest/config" />
// Noteguard frontend build (B3). The service worker (public/sw.js) is hand-written; the
// `shellManifest` plugin below only tells it which hashed build files make up the app shell.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const API = 'http://127.0.0.1:8000';
const REPO = resolve(__dirname, '..');

/** Writes dist/sw.js with the list of built app-shell files (static assets only, never /api/). */
function shellManifest(): Plugin {
  let outDir = 'dist';
  return {
    name: 'noteguard-shell-manifest',
    apply: 'build',
    configResolved(c) {
      outDir = resolve(c.root, c.build.outDir);
    },
    writeBundle(_opts, bundle) {
      const files = Object.keys(bundle).filter((f) => !f.endsWith('.map') && f !== 'sw.js');
      const icons = ['/icons/icon.svg', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/icon-maskable-512.png'];
      const shell = ['/offline.html', '/manifest.webmanifest', ...icons, ...files.map((f) => `/${f}`)];
      const swPath = resolve(outDir, 'sw.js');
      const src = readFileSync(swPath, 'utf-8');
      const version = String(files.sort().join('|').length) + '-' + String(Date.now());
      writeFileSync(swPath, src.replace('self.__SHELL__ = [];', `self.__SHELL__ = ${JSON.stringify(shell)};`)
        .replace("self.__SHELL_VERSION__ = 'dev';", `self.__SHELL_VERSION__ = ${JSON.stringify(version)};`));
    },
  };
}

export default defineConfig({
  plugins: [react(), shellManifest()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: API, changeOrigin: false } },
    // The demonstrator login picker reads the synthetic roster from fixtures/encounters/clinic.json.
    fs: { allow: [resolve(__dirname), resolve(REPO, 'fixtures', 'encounters')] },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy: { '/api': { target: API, changeOrigin: false } },
  },
  build: { sourcemap: false, target: 'es2022' },
  test: {
    environment: 'jsdom',
    // Node 25+ defines its own global localStorage/sessionStorage (undefined unless --localstorage-file
    // is given). It shadows jsdom's, so every storage reference in a test would hit Node's instead of
    // the simulated browser's. Turn Node's off in the test workers so tests see jsdom's, as on Node 22.
    poolOptions: {
      forks: { execArgv: Number(process.versions.node.split('.')[0]) >= 25 ? ['--no-experimental-webstorage'] : [] },
    },
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
    restoreMocks: true,
  },
});
