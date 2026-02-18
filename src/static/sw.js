// Service Worker for GarudaAI PWA
const CACHE_NAME = 'garudaai-v1';
const FILES_TO_CACHE = [
    '/',
    '/index.html',
    '/style.css',
    '/script.js',
    '/manifest.json',
];

// Install Service Worker
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(FILES_TO_CACHE).catch(err => {
                console.log('Cache failed, continuing:', err);
            });
        })
    );
    self.skipWaiting();
});

// Activate Service Worker
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch Event - Network first, cache fallback
self.addEventListener('fetch', event => {
    // Skip WebSocket requests
    if (event.request.url.includes('/ws/')) {
        return;
    }

    event.respondWith(
        fetch(event.request).then(response => {
            // Cache successful responses
            if (response.status === 200) {
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, responseClone);
                });
            }
            return response;
        }).catch(() => {
            // Return cached version if offline
            return caches.match(event.request).then(response => {
                return response || new Response('Offline - cached version not available', {
                    status: 503,
                    statusText: 'Service Unavailable',
                });
            });
        })
    );
});
