/*
 * Where the API lives.
 *
 * The UI is deployed twice from this one `static/` directory: to Vercel as the
 * public frontend, and by FastAPI itself (`app/main.py` mounts this directory
 * at "/") so the *.onrender.com URL and local `uvicorn` keep working unchanged.
 * Those two cases differ only in whether the API shares the page's origin, so
 * that is the one thing decided here, at runtime -- no build step, no second
 * copy of this file to keep in sync.
 *
 * Why the split is worth it: on Render's free plan the service sleeps after 15
 * idle minutes and takes about a minute to wake. Served from Render, the page
 * *itself* waits on that wake, so a visitor stares at a blank "starting" screen
 * and the app looks broken. Served from Vercel's CDN the page paints at once and
 * its own boot fetches below start the wake immediately -- which then runs while
 * the visitor is reading the page and typing a search term, rather than in front
 * of nothing. The "waking the server" notice (armWaking in app.js) covers what
 * is left.
 */
(function () {
  // The Render service's hostname, from `name:` in render.yaml. Change it here,
  // in this one place, if the service is renamed or moved to a custom domain.
  var API_ORIGIN = "https://pasuk-leshem.onrender.com";

  var host = window.location.hostname;
  var sameOrigin =
    /(^|\.)onrender\.com$/.test(host) ||
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "";  // file://, and anything else without a host

  // An explicit override wins over both, so the cross-origin path can be
  // exercised locally (`localStorage.setItem("apiBase", "http://localhost:8000")`)
  // without editing this file. Empty string is a meaningful value -- "same
  // origin" -- so this deliberately tests for null rather than for falsiness.
  var override = null;
  try {
    override = window.localStorage.getItem("apiBase");
  } catch (e) {
    /* storage disabled (private mode, blocked cookies) -- fall through */
  }

  window.API_BASE = override !== null ? override : sameOrigin ? "" : API_ORIGIN;
})();
