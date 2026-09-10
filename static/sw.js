/*
 * פסוק לשם — service worker.
 *
 * Two jobs:
 *
 *  1. Satisfy the browser's PWA installability check -- a registered worker
 *     with a fetch handler is still what some browsers gate the install prompt
 *     on.
 *  2. Keep a copy of the app shell, so tapping the installed icon paints the UI
 *     straight away rather than waiting on a round trip -- including while the
 *     API is still waking up (see static/config.js) or with no network at all.
 *
 * Network-first, cache only as a fallback. That ordering is the point: it
 * preserves the deploy-immediacy this app is otherwise careful about (the page
 * and its assets are served with Cache-Control: no-cache), because a reachable
 * network always wins and the cache answers only when the request fails
 * outright. A cached shell can therefore never outlive a deploy the way a
 * cache-first worker's would.
 *
 * The API is deliberately excluded: a search result is not the app, and a stale
 * one would be worse than an honest error.
 */
var CACHE = "pasuk-leshem-shell-v1";

// Enough to render the page and have it ask for data. Fonts and icons are not
// listed -- they get cached opportunistically below if and when they are used.
var SHELL = [
  "/",
  "/index.html",
  "/config.js",
  "/i18n.js",
  "/app.js",
  "/styles.css",
  "/manifest.json",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(CACHE)
      .then(function (cache) { return cache.addAll(SHELL); })
      // One asset failing to precache must not leave the worker uninstalled --
      // the fetch handler below re-caches whatever is actually used anyway.
      .catch(function () {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys.map(function (key) { return key === CACHE ? null : caches.delete(key); })
        );
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  var url = new URL(request.url);

  // Left entirely alone: anything that isn't a plain same-origin GET, and the
  // API in particular. Note the API is same-origin when this page is served by
  // the app itself (Render, local uvicorn) and cross-origin when it is served
  // from Vercel -- this check has to catch the first case, the origin test
  // already covers the second.
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.indexOf("/api/") === 0
  ) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then(function (response) {
        if (response && response.ok) {
          var copy = response.clone();
          caches.open(CACHE).then(function (cache) { cache.put(request, copy); });
        }
        return response;
      })
      .catch(function () {
        return caches.match(request).then(function (hit) {
          if (hit) return hit;
          // A navigation with nothing cached for that exact URL still deserves
          // the app rather than the browser's offline page.
          if (request.mode === "navigate") return caches.match("/index.html");
          return Response.error();
        });
      })
  );
});
