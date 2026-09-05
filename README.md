# פסוק לשם — Tanakh verses for a name

A mobile-first Hebrew web app for the custom of saying a verse that matches your
name: a verse whose **first letter** matches the name's first letter and whose
**last letter** matches its last letter, traditionally recited at the end of the
Amidah. It also finds verses that contain the name outright, and — for two or
three names, comma-separated — pairs of **consecutive verses** matching two of
them in order.

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
An O(1) lookup against an index built at startup. A query with no comma but
more than one word (e.g. `אסתר מלכה`) is one compound name: whitespace is
stripped before the comparison, so its first letter is the first letter of its
first word and its last letter is the last letter of its last word — the
traditional reading of a multi-word name, not two separate names.

**Name in verse**, in two tiers, because raw substring matching is very noisy —
`שרה` appears as a bare substring in 918 verses (matching `אשרה`, `ישרה`, and the
verb `שרה`):

| Tier | Rule | `שרה` |
| --- | --- | --- |
| `exactWord` | the name as a standalone word | 28 verses |
| `partialWord` | inside a longer word — covers ו/ה/ב/כ/ל/מ/ש prefixes and suffixes | 244 verses |

The tiers never overlap, and the clean matches lead.

**Pairs**, for two or three comma-separated names. Consecutive verses are
genuinely rare — `אברהם, שרה` yields exactly **one** pair in the whole Tanakh,
and many name pairs yield none — so the search is widened into three labelled
groups per pair of names:

- `consecutive` — verse N matches name 1, verse N+1 matches name 2. Both verses
  must be in the same book, but they may cross a chapter boundary, since the last
  verse of a chapter and the first of the next really are consecutive.
- `reversed` — the same, with the names swapped.
- `nearMiss` — one verse in between (N and N+2).

With **three names**, every combination of two of them is checked (three
combinations), each labeled with which two names it covers, rather than
requiring all three in a row — a three-way consecutive run would be rarer
still on top of an already-rare pair. `אברהם, יצחק, יעקב` (Abraham, Isaac,
Jacob) turns up nothing for Abraham+Isaac, a near-miss for Abraham+Jacob
(Proverbs 24:19, 21), and a genuine consecutive pair for Isaac+Jacob
(Job 39:21–22).

## API

The UI is a client of this API; nothing is private to it.

```http
GET /api/search?names=אברהם,שרה&limit=100
GET /api/random?name=דוד
GET /api/health
```

Names are separated by `,`, `،` or `;` — one name, or up to three. Errors come
back as `{"error": "…", "code": "…"}` — `error` is a Hebrew message ready to
display as-is; `code` (`empty` | `too_many` | `invalid_name` | `not_found`) is
a stable string the frontend uses to show the same error in whichever of
Hebrew/English/French the UI is currently in.

```jsonc
{
  "query": { "names": ["אברהם", "יצחק", "יעקב"], "mode": "multi" },  // "single" for one name
  "pairs": [
    // one entry per combination of two of the names (three names -> three entries)
    { "names": ["אברהם", "יצחק"],
      "consecutive": [ { "first": {…}, "second": {…},
                         "firstName": "אברהם", "secondName": "יצחק",
                         "crossesChapter": false } ],
      "reversed": [ … ],
      "nearMiss": [ … ] },
    { "names": ["אברהם", "יעקב"], "consecutive": [ … ], "reversed": [ … ], "nearMiss": [ … ] },
    { "names": ["יצחק", "יעקב"], "consecutive": [ … ], "reversed": [ … ], "nearMiss": [ … ] }
  ],
  "names": [
    { "name": "אברהם", "first": "א", "last": "מ",
      "letterMatch": { "total": 297, "verses": [ … ] },   // capped by `limit`,
      "exactWord":   { "total": 128, "verses": [ … ] },   // `total` is the true count
      "partialWord": { "total":  31, "verses": [ … ] } },
    { "name": "יצחק", … },
    { "name": "יעקב", … }
  ]
}
```

A verse:

```jsonc
{
  "book": { "he": "בראשית", "en": "Genesis", "fr": "Genèse" },
  "section": "תורה",
  "chapter": 2, "verse": 4,                 // plain integers, for an en/fr locale
  "chapterHe": "ב׳", "verseHe": "ד׳",        // gematria, for the he locale
  "ref": "בראשית ב׳:ד׳",          // the citation form -- always Hebrew gematria,
                                   // regardless of UI language (ט״ו and ט״ז included)
  "text": "אֵ֣לֶּה תוֹלְד֧וֹת …",
  "highlights": [ { "start": 0, "end": 3, "kind": "first" },   // kind: first | last | name
                  { "start": 112, "end": 113, "kind": "last" } ]
}
```

## Language

The UI is available in Hebrew, English and French (`static/i18n.js`, a plain
string table with `{token}` interpolation and one/two/other pluralization —
Hebrew has a dedicated dual form, e.g. "שני פסוקים" rather than "2 פסוקים").
Switching language re-renders the current results from the last response
already in hand, with no new request to the server.

Two things never translate, on purpose: **the verse text**, and **its
citation** (`ref`, e.g. `בראשית ב׳:ד׳`) — always Hebrew, gematria included,
the same as the custom this app is for. Everything else is UI chrome and
follows the selected language: labels, buttons, group headings, error
messages, and even the book name badge (`verse.book.he/en/fr`, sourced from
Sefaria's English title and — since Sefaria doesn't provide one — a French
name supplied in `scripts/build_dataset.py`). The chapter/verse badges switch
between Hebrew gematria and plain digits with the language (`chapterHe`/`verseHe`
vs. `chapter`/`verse`).

Server error codes exist specifically so validation messages ("enter a name
using Hebrew letters") can be localized too, rather than always coming back in
Hebrew regardless of the UI language.

The chosen language persists in `localStorage` and defaults to Hebrew. The
example chips (אברהם, שרה, …) are never translated in any locale — they're
input examples for a field that only ever accepts Hebrew names, not UI text.

## In-app help

A collapsed **"How does this work?"** disclosure sits under the search hint
(native `<details>`, so it needs no JS to open), explaining the two input
rules: no comma is one compound name (first letter of the first word, last
letter of the last word); a comma means separate names, and triggers the
consecutive-verse search.

Each result group can also carry a collapsed **"Example"** disclosure of its
own (`I18N.example(locale, key)` in `static/i18n.js`) — closed by default, and
simply absent when no text has been supplied for that group yet. The lookup
table (`EXAMPLES` in `i18n.js`) currently has no entries; add a `{he, en, fr}`
object under the relevant key (`group.letterMatch`, `group.exactWord`,
`group.partialWord`, `pair.consecutive`, `pair.reversed`, `pair.nearMiss`) to
have that group's toggle appear.

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
when idle, so the first request after a while pays a cold start (up to ~a minute).
The UI accounts for this itself: if a request is still pending after 2.5s, it shows
a "waking the server" notice rather than looking frozen, and clears it the moment
the response arrives (`armWaking`/`disarmWaking` in `static/app.js`).

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
