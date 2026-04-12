/* ══════════════════════════════════════════
   AgriShield AI — Service Worker
   Offline support + PWA install guarantee
══════════════════════════════════════════ */

const CACHE_NAME = 'agrishield-v1';

const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  'https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap'
];

/* ── INSTALL: cache static assets ── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

/* ── ACTIVATE: clean old caches ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

/* ── FETCH: network first, fallback to cache ── */
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  /* Always go network-first for API calls (/predict, /download-report) */
  if (url.pathname.startsWith('/predict') || url.pathname.startsWith('/download-report')) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: 'You are offline. Please reconnect to analyze crops.' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    return;
  }

  /* For everything else: network first, then cache fallback */
  event.respondWith(
    fetch(event.request)
      .then(response => {
        /* Cache successful GET responses */
        if (event.request.method === 'GET' && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});