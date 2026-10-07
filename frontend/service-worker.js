const CACHE_NAME = 'waste-segregator-v25';
// v25: index.html gained the admin math-challenge UI and the forced
// password-change dialog. index.html is precached, so without this bump a
// browser would keep replaying the old login page and never show either.
// v20: login/register loading overlay. login-loader.{css,js} are precached so the
// overlay never paints without its stylesheet on a cold/offline start, and the
// blurred loader-bg.jpg is precached for the same reason.
// v19: purge stale cached HTML. This app is cache-first, so a browser that had
// cached /dashboard.html (and any other page) from an earlier build keeps
// replaying that copy even after the server stops sending it. Bumping the cache
// name makes 'activate' delete the old cache, so clients re-fetch from network.
// v18: JUNO AI chat avatars (juno.png / juno-dark.png) added to the precache
// for offline support-chat rendering.
// v17: favicon set. New generated icon files (/frontend/assets/images/favicon-*,
// apple-touch-icon.png, icon-*.png, icon-maskable-512.png, favicon.ico) are now
// cached for offline install, and every page gained <link rel="icon"> tags.
// v16: unified sidebar footer.

// The full installable shell: every HTML page, the shared CSS/JS, PWA assets
// and the manifest. All paths are absolute from the site root. Pages render
// from Jinja2 templates, so they are cached under their canonical routes
// (/dashboard.html, /pages/<page>.html) — the old /frontend/... locations
// redirect there.
const urlsToCache = [
  // Shell
  '/',
  '/frontend/index.html',
  '/frontend/register.html',
  '/dashboard.html',
  // Pages
  '/pages/analytics.html',
  '/pages/dry-bin.html',
  '/pages/guide.html',
  '/pages/help.html',
  '/pages/impact.html',
  '/pages/leaderboard.html',
  '/pages/locations.html',
  '/pages/maintenance.html',
  '/pages/map.html',
  '/pages/notifications.html',
  '/pages/profile.html',
  '/pages/reports.html',
  '/pages/settings.html',
  '/pages/users.html',
  '/pages/wet-bin.html',
  '/pages/404.html',
  // Shared CSS / JS
  '/frontend/shared/css/themes.css',
  '/frontend/shared/css/animations.css',
  '/frontend/shared/css/login-loader.css',
  '/frontend/assets/images/loader-bg.jpg',
  '/frontend/shared/js/utils.js',
  '/frontend/shared/js/pwa.js',
  '/frontend/shared/js/chat-widget.js',
  '/frontend/shared/js/emailjs-config.js',
  '/frontend/shared/js/chart-theme.js',
  '/frontend/shared/js/login-loader.js',
  // PWA assets
  '/frontend/assets/images/logo.png',
  '/frontend/assets/images/logo-dark.png',
  '/frontend/assets/images/juno.png',
  '/frontend/assets/images/juno-dark.png',
  '/frontend/assets/images/bin-wet.svg',
  '/frontend/assets/images/favicon-16x16.png',
  '/frontend/assets/images/favicon-32x32.png',
  '/frontend/assets/images/apple-touch-icon.png',
  '/frontend/assets/images/icon-192.png',
  '/frontend/assets/images/icon-512.png',
  '/frontend/assets/images/icon-maskable-512.png',
  '/favicon.ico',
  '/frontend/manifest.json'
];

// Install event - cache files (gracefully handle missing files)
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        // Use individual adds to avoid failing on missing files
        return Promise.allSettled(
          urlsToCache.map(url => cache.add(url).catch(err => {
            console.warn('Failed to cache:', url, err);
          }))
        );
      })
  );
  self.skipWaiting();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
  // Skip cross-origin requests (Google Fonts, Chart.js CDN, Leaflet CDN, etc.)
  if (!event.request.url.startsWith(self.location.origin)) return;

  // Never intercept non-GET (POST /api/sensor-data must reach the network)
  if (event.request.method !== 'GET') return;

  // NEVER cache or replay dynamic API responses (auth state, live readings,
  // settings, etc.). A stale cached /api/auth/me would mask a logout and keep
  // the user "logged in" forever. Always hit the network for /api/*.
  if (event.request.url.includes('/api/')) return;

  // Never cache user-uploaded profile pictures, otherwise a fresh upload with
  // the same URL would keep showing the previous image (cache-first replay).
  if (event.request.url.includes('/uploads/')) return;

  // NEVER intercept media requests (HTML5 <video>/<audio>). They send Range
  // headers (bytes=...), and caches.match() keys on the URL only — ignoring
  // Range — so a later range request could be answered with an earlier cached
  // 206 partial for the wrong byte range, corrupting playback (ERR_ABORTED).
  // Always fetch media from the network.
  if (event.request.headers.has('range')) return;

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          // Update cache in background (stale-while-revalidate)
          event.waitUntil(
            fetch(event.request).then(networkResponse => {
              if (networkResponse.ok) {
                caches.open(CACHE_NAME).then(cache => {
                  cache.put(event.request, networkResponse);
                });
              }
            }).catch(() => {})
          );
          return response;
        }
        return fetch(event.request).then(networkResponse => {
          // Cache successful HTML/CSS/JS responses
          if (networkResponse.ok) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        });
      })
      .catch(() => {
        // Offline fallback for navigation requests
        if (event.request.mode === 'navigate') {
          return caches.match('/frontend/dashboard.html');
        }
      })
  );
});

// Activate event - clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Message from the page (pwa.js) asking the waiting SW to take over
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Push notification
self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: 'Smart Waste Segregator Alert', body: event.data ? event.data.text() : 'New notification' };
  }

  const options = {
    body: data.body || 'Check your bins',
    icon: '/frontend/assets/images/logo.png',
    badge: '/frontend/assets/images/bin-wet.svg',
    vibrate: [200, 100, 200],
    data: {
      url: data.url || '/frontend/dashboard.html'
    }
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Smart Waste Segregator', options)
  );
});

// Notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/frontend/dashboard.html')
  );
});