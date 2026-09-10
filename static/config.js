/*
 * Where the API lives: the same origin as this page, always.
 *
 * The UI is deployed twice from this one `static/` directory -- by the app
 * itself (`app/main.py` mounts it at "/") and to Vercel as the public frontend.
 * Both are same-origin with the API, because `vercel.json` rewrites `/api/*`
 * to the Render service. The browser only ever talks to the origin it loaded
 * the page from; Vercel's edge makes the hop to Render server-side.
 *
 * That indirection is the point. The first attempt had the page call Render
 * directly, which is a cross-origin request and so subject to CORS -- and
 * cross-origin was where it broke, with the browser refusing the request
 * before any of this code could see why ("TypeError: Failed to fetch" is all
 * the JS gets; the reason stays in the console). Proxying does not configure
 * CORS correctly, it removes CORS from the path entirely: no allowlist to
 * match, no preflight to pass, and nothing that has to be re-pointed when the
 * frontend's hostname changes.
 *
 * The remaining reason this file exists is the override below, which makes a
 * genuinely split setup testable without a proxy in front of it.
 */
(function () {
  var override = null;
  try {
    // e.g. localStorage.setItem("apiBase", "http://localhost:8000") to point a
    // locally-served page at an API on another port. Empty string is a
    // meaningful value -- "same origin" -- so this tests for null rather than
    // for falsiness.
    override = window.localStorage.getItem("apiBase");
  } catch (e) {
    /* storage disabled (private mode, blocked cookies) -- fall through */
  }

  window.API_BASE = override !== null ? override : "";
})();
