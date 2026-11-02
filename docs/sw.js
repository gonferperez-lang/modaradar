/* Service worker: la app abre al instante y funciona sin conexión con los últimos datos. */
const VERSION = 'modaradar-v1';
const SHELL = ['./', 'index.html', 'styles.css', 'app.js', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  // Datos y código: primero la red (siempre lo último), con copia de respaldo sin conexión.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          const key = url.pathname.includes('/data/') ? url.origin + url.pathname : e.request;
          caches.open(VERSION).then((c) => c.put(key, copy));
        }
        return res;
      })
      .catch(() => caches.match(url.pathname.includes('/data/') ? url.origin + url.pathname : e.request)),
  );
});
