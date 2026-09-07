/*
 * פסוק לשם — minimal service worker.
 *
 * Its only job is to satisfy the browser's PWA installability check (a
 * registered service worker with a fetch handler is still what some
 * browsers gate the install prompt on). It does not cache anything or work
 * offline -- every search is a live API call against a corpus that only
 * lives on the server, so there is nothing meaningful to serve without a
 * network anyway.
 */

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  event.respondWith(fetch(event.request));
});
