/* Noteguard service worker (B3). Hand-written so the cache policy can be audited in one screen.
 *
 * Policy (Section 4, 10.2):
 *  - It caches ONLY the static app shell: the hashed build files, the offline page, the manifest and
 *    icons, listed explicitly at build time (vite.config.ts replaces the empty list below).
 *  - Anything under /api/ is never served from the cache and never written to it: the handler
 *    returns without calling respondWith, so the browser goes to the network as if no SW existed.
 *  - Non-GET requests and other origins are left alone the same way.
 *  - There is no runtime caching at all (no cache.put): only the install step writes the cache.
 *  - Navigations are network-first; when offline they get the static offline page, which holds no
 *    clinical content.
 */
self.__SHELL__ = [];
self.__SHELL_VERSION__ = 'dev';

const CACHE = 'noteguard-shell-' + self.__SHELL_VERSION__;
const OFFLINE_URL = '/offline.html';

function isApi(url) {
  return url.pathname === '/api' || url.pathname.startsWith('/api/');
}

function isShell(url) {
  return self.__SHELL__.indexOf(url.pathname) !== -1 && !isApi(url);
}

self.addEventListener('install', (event) => {
  const shell = self.__SHELL__.filter((p) => !isApi(new URL(p, self.location.origin)));
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(shell.length ? shell : [OFFLINE_URL]))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApi(url)) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (isShell(url)) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
  }
});
