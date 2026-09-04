# פסוק לשם — Tanakh verses for a name

A mobile-first Hebrew web app for the custom of saying a verse that matches your
name: a verse whose **first letter** matches the name's first letter and whose
**last letter** matches its last letter, traditionally recited at the end of the
Amidah. It also finds verses that contain the name outright, and — for a couple —
pairs of **consecutive verses** matching two names in order.

Everything runs from one small FastAPI service: the API and the UI are served
from the same origin, and the full Tanakh is bundled locally, so there is no CORS
setup, no external API to depend on, and no network access needed at runtime.

```
┌── static/ ────────────┐        ┌── app/ ──────────────────┐
│  index.html           │  same  │  main.py    HTTP API      │
│  styles.css           │◄──────►│  search.py  matching      │
│  app.js               │ origin │  corpus.py  index         │
└───────────────────────┘        │  hebrew.py  normalization │
                                 └──────────┬────────────────┘
                                            │ loaded once at boot
                                 ┌──────────▼────────────────┐
                                 │ data/tanakh.json.gz 1.3MB │
                                 │ 23,206 verses, 24 books   │
                                 └───────────────────────────┘
```

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. That is the whole setup — the corpus is already in
the repository, and the frontend has no build step.

### On your phone, over the local network

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Find your machine's LAN address and open `http://<that-address>:8000` on the
phone, with both devices on the same Wi-Fi:

```bash
hostname -I | awk '{print $1}'          # Linux
ipconfig getifaddr en0                  # macOS
```

## How the Tanakh is packaged and loaded

| | |
| --- | --- |
| **Text** | "תנ״ך עם טעמי המקרא" — the Miqra with full niqqud and cantillation |
| **Source** | [Sefaria's public export](https://github.com/Sefaria/Sefaria-Export), originally from [tanach.us](http://www.tanach.us/Tanach.xml) |
| **License** | Public Domain |
| **Size** | 23,206 verses across the 24 books (39 files), 1.3 MB gzipped |
| **Packaging** | One gzipped JSON at `data/tanakh.json.gz`, committed to the repo |
| **Loading** | Read and indexed once at process start (~1.5 s), then held in memory |

`scripts/build_dataset.py` is what produced that file. It is a **build-time**
tool, not part of the running app — run it only to refresh the corpus:

```bash
python scripts/build_dataset.py
```

Because the data is committed, the running application never makes a network
call, a fresh clone works offline, and the phone downloads roughly 30 KB of
matched verses per search rather than the whole Tanakh.

### The text is cleaned at build time

The raw export carries editorial apparatus that has to come out, or it corrupts
the very thing this app matches on. `clean_verse()` in the build script handles
each case, and `tests/test_search.py::TestCleanedText` guards them:

- **`(פ)` and `(ס)` parasha markers** sit after the sof pasuq in 3,124 verses.
  Since פ and ס *are* Hebrew letters, leaving them in gave **3,048 verses the
  wrong final letter** — 13% of the corpus, silently breaking the primary search.
- **Ketiv/qere** — the unpointed ketiv followed by the pointed qere in brackets
  (`מנ הסערה [מִן ׀] [הַסְּעָרָה]`). The qere is the text as it is *read*, so the qere
  is kept. The two runs can differ in length, so the rule is "a run of unpointed
  tokens followed by a run of bracketed groups", not a one-for-one swap.
- **Ketiv velo qere** — written but not read, with no qere given (Ruth 3:12 `אם`).
  Dropped.
- **Qere velo ketiv** — read but not written, bracketed with no ketiv before it
  (Ruth 3:5 `[אֵלַי]`). Kept, brackets removed.
- **`<br><small>…`** — Lamentations 5:22 and Ecclesiastes 12:14 append the
  penultimate verse, per the custom of not ending on a harsh note. Removed.
- **U+200D zero-width joiner** — would otherwise split the word around it in two.

## Hebrew normalization

`app/hebrew.py` holds the primitives, all pure functions:

- **Niqqud and ta'amei hamikra** (`U+0591–U+05BD`, `U+05BF–U+05C5`, `U+05C7`) are
  stripped before any comparison.
- **Maqaf** (`־`) is deliberately *not* stripped as a mark — it joins two words,
  so it is treated as a separator. `עַל־פְּנֵי` is two words, `על` and `פני`, not one.
- **Sof pasuq** (`׃`) never counts as a verse's last letter.
- **Final letters** (מנצפ״ך סופיות) fold to their regular forms, so a name ending
  in `ם` matches a verse ending in `מ`.
- **Everything else** — geresh, gershayim, apostrophes, digits, Latin letters,
  whitespace — is dropped when identifying letter boundaries.

Highlight offsets are computed **server-side**, because mapping a position in the
normalized form back onto text that carries niqqud is fiddly enough to be worth
doing once. Each range is extended to cover the marks belonging to its letter, so
a highlighted letter never gets separated from its vowel.

## Matching

**Letter match** (the primary custom) — first and last letters, finals folded.
An O(1) lookup against an index built at startup.

**Name in verse**, in two tiers, because raw substring matching is very noisy —
`שרה` appears as a bare substring in 918 verses (matching `אשרה`, `ישרה`, and the
verb `שרה`):

| Tier | Rule | `שרה` |
| --- | --- | --- |
| `exactWord` | the name as a standalone word | 28 verses |
| `partialWord` | inside a longer word — covers ו/ה/ב/כ/ל/מ/ש prefixes and suffixes | 244 verses |

The tiers never overlap, and the clean matches lead.

**Pairs**, for two names. Consecutive verses are genuinely rare — `אברהם, שרה`
yields exactly **one** pair in the whole Tanakh, and many name pairs yield none —
so the search is widened into three labelled groups:

- `consecutive` — verse N matches name 1, verse N+1 matches name 2. Both verses
  must be in the same book, but they may cross a chapter boundary, since the last
  verse of a chapter and the first of the next really are consecutive.
- `reversed` — the same, with the names swapped.
- `nearMiss` — one verse in between (N and N+2).

## API

The UI is a client of this API; nothing is private to it.

```http
GET /api/search?names=אברהם,שרה&limit=100
GET /api/random?name=דוד
GET /api/health
```

Names are separated by `,`, `،` or `;`. Errors come back as
`{"error": "…"}` with a Hebrew message, ready to display.

```jsonc
{
  "query":  { "names": ["אברהם", "שרה"], "mode": "pair" },
  "pairs":  {
    "consecutive": [ { "first": {…}, "second": {…},
                       "firstName": "אברהם", "secondName": "שרה",
                       "crossesChapter": false } ],
    "reversed": [ … ],
    "nearMiss": [ … ]
  },
  "names": [
    { "name": "אברהם", "first": "א", "last": "מ",
      "letterMatch": { "total": 297, "verses": [ … ] },   // capped by `limit`,
      "exactWord":   { "total": 128, "verses": [ … ] },   // `total` is the true count
      "partialWord": { "total":  31, "verses": [ … ] } }
  ]
}
```

A verse:

```jsonc
{
  "book": "בראשית", "section": "תורה",
  "chapter": 2, "verse": 4,
  "ref": "בראשית ב׳:ד׳",          // Hebrew numerals, ט״ו and ט״ז included
  "text": "אֵ֣לֶּה תוֹלְד֧וֹת …",
  "highlights": [ { "start": 0, "end": 3, "kind": "first" },   // kind: first | last | name
                  { "start": 112, "end": 113, "kind": "last" } ]
}
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

61 tests, run against the real committed corpus rather than a fixture — the point
of most of them is that the actual Tanakh gives the expected answer: `אברהם`
matches 297 verses, `שרה` 76, `דוד` 4, and `אברהם, שרה` has exactly one
consecutive pair.

## Deploying

**Render** — `render.yaml` is a blueprint; point Render at the repo and it builds
and starts with a `/api/health` health check. On the free plan the service sleeps
when idle, so the first request after a while pays a cold start.

**Docker** — the corpus is baked into the image, so the container needs no
network access:

```bash
docker build -t pasuk-leshem .
docker run -p 8000:8000 pasuk-leshem
```

**Anywhere else** — it is one ASGI app with two dependencies:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Fly.io, Railway and
Deta all take it as-is. Vercel is a poor fit: its Python runtime is
serverless, so the 1.5 s corpus load would run on cold starts.

## Layout

```
app/hebrew.py           normalization, offsets, Hebrew numerals  (no deps)
app/corpus.py           gzip load + the two search indexes
app/search.py           letter match, name-in-verse, pairs, highlighting
app/main.py             FastAPI routes; mounts static/ at "/"
scripts/build_dataset.py   Sefaria export -> data/tanakh.json.gz (build-time)
static/                 the UI: one page, one stylesheet, one script
tests/                  pytest, against the real corpus
```

## Notes

- The frontend keeps the query in the URL hash (`#q=אברהם,שרה`), so a result is
  shareable and the back button moves between searches.
- Results are capped per group (`limit`, default 100) with the true total
  reported alongside; the UI shows the first 10 and reveals the rest on request.
- Text is public domain. The code is available under the MIT license.
