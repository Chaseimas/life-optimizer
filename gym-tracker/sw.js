// BUMP CACHE_NAME on ANY deploy that changes manifest.json or the icons —
// those are served cache-first and only refresh when a changed sw.js reinstalls.
// (index.html updates flow through the network-first navigate branch automatically.)
const CACHE_NAME = 'ironlog-v2';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];
const NAV_TIMEOUT_MS = 2500;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const isShell = e.request.mode === 'navigate' || e.request.url.endsWith('/index.html');
  if (isShell) {
    // network-first with a short timeout so a stalled gym connection can't hang
    // launch; fresh copies land under the canonical './index.html' key; HTTP
    // error pages (Pages deploy 404s) fall back to the cached shell too
    const net = fetch(e.request).then(response => {
      if (response.status === 200) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put('./index.html', clone.clone());
          cache.put('./', clone);
        });
      }
      return response;
    }).catch(() => null);
    e.respondWith((async () => {
      const timer = new Promise(res => setTimeout(() => res('timeout'), NAV_TIMEOUT_MS));
      const first = await Promise.race([net, timer]);
      if (first && first !== 'timeout' && first.status === 200) return first;
      const cached = await caches.match('./index.html') || await caches.match(e.request);
      if (cached) return cached;
      const late = await net;
      return late || Response.error();
    })());
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(response => {
        if (response.status === 200 && e.request.url.startsWith(self.location.origin)) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
        }
        return response;
      });
    })
  );
});
