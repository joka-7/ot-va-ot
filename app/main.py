"""FastAPI application.

Serves the JSON search API and the mobile web UI from the *same origin*, which
is what keeps CORS out of the picture entirely — the page and the API it calls
share a host, so a phone browser never sees a cross-origin request.
"""

from __future__ import annotations

import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .corpus import load_corpus
from .search import DEFAULT_LIMIT, MAX_LIMIT, MAX_NAMES, Name, letter_highlights, search, serialize

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Names may be separated by a comma (Latin or Arabic) or a semicolon.
SEPARATORS = ",،;"

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load and index the corpus at boot, rather than on the first request.

    Roughly 1.5 seconds of work that would otherwise land on whoever searches
    first — on a cold-starting host, that is the user.
    """
    corpus = load_corpus()
    print(f"Loaded {len(corpus):,} verses from {len(corpus.books)} books.")
    yield


app = FastAPI(
    title="פסוק לשם",
    description="Finds Tanakh verses matching a personal name, per the Jewish custom.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def no_cache_static_assets(request, call_next):
    """Force revalidation on every load of the page and its static assets.

    static/*.js and static/*.css have no cache-busting in their URLs -- they
    are always "/app.js", "/i18n.js", "/styles.css" -- so without this, a
    browser (or an intermediate cache) that already has a copy can go on
    serving it after a deploy changes the file's content. A translation key
    added to i18n.js today would then render as its own literal key name in
    a browser holding yesterday's cached copy, until that cache happened to
    expire.

    "no-cache" does not mean "don't cache" -- the browser still keeps its
    copy, but must revalidate with the server (a cheap conditional request)
    before using it, so a change always takes effect on the next load.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache"
    return response


def error(code: str, message: str) -> dict:
    """An HTTPException detail carrying both a Hebrew message, for a direct API
    caller, and a stable machine-readable code the frontend can localize into
    whichever of Hebrew/English/French the UI is currently showing.
    """
    return {"code": code, "message": message}


def parse_names(raw: str) -> list[Name]:
    """Split the query into one or two validated names."""
    for separator in SEPARATORS[1:]:
        raw = raw.replace(separator, SEPARATORS[0])
    parts = [part.strip() for part in raw.split(SEPARATORS[0])]
    parts = [part for part in parts if part]

    if not parts:
        raise HTTPException(status_code=400, detail=error("empty", "לא הוזן שם לחיפוש"))
    if len(parts) > MAX_NAMES:
        raise HTTPException(
            status_code=400, detail=error("too_many", "אפשר לחפש בין שם אחד לשלושה שמות")
        )

    try:
        return [Name.parse(part) for part in parts]
    except ValueError:
        raise HTTPException(
            status_code=400, detail=error("invalid_name", "יש להזין שם באותיות עבריות")
        ) from None


@app.get("/api/health")
def health() -> dict:
    """Liveness check that also reports what corpus is loaded."""
    corpus = load_corpus()
    return {
        "status": "ok",
        "verses": len(corpus),
        "books": len(corpus.books),
        "version": corpus.version,
        "source": corpus.source,
        "license": corpus.license,
    }


@app.get("/api/search")
def search_endpoint(
    names: str = Query(..., description="One name, or two separated by a comma"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    """Search the Tanakh for verses matching one or two names."""
    return search(load_corpus(), parse_names(names), limit=limit)


@app.get("/api/random")
def random_endpoint(name: str = Query(..., description="A single name")) -> dict:
    """One random verse whose first and last letters match the name.

    Used by the UI's empty state to show the custom in action.
    """
    corpus = load_corpus()
    parsed = parse_names(name)[0]
    matches = corpus.letter_matches(parsed.first, parsed.last)
    if not matches:
        raise HTTPException(status_code=404, detail=error("not_found", "לא נמצא פסוק מתאים"))
    verse = corpus.verses[random.choice(matches)]
    return {"name": parsed.raw, "verse": serialize(verse, letter_highlights(verse))}


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    """Return errors as {"error": "<hebrew message>", "code": "<stable code>"}.

    ``error`` is kept as a plain Hebrew string for a direct API caller (and for
    backward compatibility); ``code`` lets the frontend show the message in
    whichever locale the UI is currently in. ``code`` is null for an
    HTTPException raised outside this module, which won't carry one.
    """
    detail = exc.detail
    if isinstance(detail, dict):
        content = {"error": detail.get("message", ""), "code": detail.get("code")}
    else:
        content = {"error": detail, "code": None}
    return JSONResponse(status_code=exc.status_code, content=content)


# Mounted last so that /api/* routes win; html=True serves index.html at "/".
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
