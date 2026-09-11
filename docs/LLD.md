# Low-level design — אות ואות

Per-module contracts, the exact response shapes, and the non-obvious logic.
System-level context is in [`HLD.md`](HLD.md).

## `app/hebrew.py` — normalization primitives

Pure functions over `str`. No knowledge of verses, HTTP, or the corpus.

| Function | Contract |
| --- | --- |
| `strip_marks(text)` | Drop niqqud and cantillation, keep letters and spacing |
| `letters_only(text)` | Hebrew letters only — no marks, punctuation or spaces |
| `normalize_finals(text)` | Fold ך ם ן ף ץ onto כ מ נ פ צ |
| `normalize(text)` | `letters_only` + `normalize_finals` — the comparison form |
| `words(text)` | Normalized words, in order |
| `first_last(text)` | `(first letter, last letter)` of the whole string, finals folded |
| `has_hebrew(text)` | Whether any Hebrew letter is present |
| `he_number(value)` | Integer → gematria (`15 → ט״ו`, not `יה`) |
| `is_letter` / `is_mark` | Single-character classification |
| `mark_end(text, index)` | Index just past the marks attached to the letter at `index` |
| `letter_positions(text)` | Indices of every Hebrew letter |
| `word_spans(text)` | `Word` objects carrying each word's normalized form and offsets |

**Why final-letter folding is load-bearing.** A name ending in ן must match
a verse ending in נ — the same letter, positionally spelled. Every
comparison in `search.py` runs on `normalize`d text, so this happens once
here rather than at each call site.

**Why maqaf (`־`) is a separator, not a stripped mark.** It joins two words
in the source text (`עַל־פְּנֵי`). Stripping it like an ordinary mark would fuse
the two words into one for matching purposes; treating it as a boundary
keeps `על` and `פני` as two words, matching how a reader would say them.

**`he_number` special case.** 15 and 16 are written ט״ו and ט״ז rather than
יה and יו, which would spell a divine name. The function short-circuits
both before reaching the general gematira table.

## `app/corpus.py` — model and indexes

### `Verse`

A `__slots__` record. Beyond the raw fields (`book`, `book_en`, `book_fr`,
`section`, `chapter`, `number`, `text`, `rashi`) it precomputes at load
time:

- `letters` — `normalize(text)`, the comparison form
- `first`, `last` — the folded first and last letters
- `word_list`, `word_set` — normalized words, tuple and frozenset
- `chapter_he`, `verse_he`, `ref` — gematira forms and the citation string

Precomputing is the reason search is fast: the per-verse string work
happens once at boot for all ~23,206 verses, never per request. `rashi` is
carried as pre-cleaned HTML (see `scripts/build_dataset.py`) or `""` when
Rashi wrote nothing on that verse.

### `Corpus`

```python
Corpus(dataset: dict[str, Any])
```

Builds two indexes while walking the verses:

| Index | Type | Serves |
| --- | --- | --- |
| `by_letter_pair` | `dict[tuple[str, str], list[int]]` | `letter_matches(first, last)` |
| `by_word` | `dict[str, list[int]]` | `exact_word_matches(name)` |

| Method | Contract |
| --- | --- |
| `letter_matches(first, last)` | Verse ids opening with `first`, closing with `last` — dict hit |
| `exact_word_matches(name)` | Verse ids where `name` is a whole normalized word — dict hit |
| `partial_word_matches(name)` | Verse ids where `name` is a substring of a longer word, excluding exact matches — linear scan, the one unindexed path |
| `neighbour(verse, offset)` | The verse `offset` positions away, or `None` if that crosses a book boundary |
| `__len__` | Verse count |

`neighbour` deliberately allows crossing a *chapter* boundary but not a
*book* one: the last verse of a chapter and the first of the next genuinely
are consecutive, whereas two different books are not.

`load_corpus(path=None)` is `@functools.lru_cache(maxsize=1)`, so the gzip
read and the whole indexing pass happen once per process. Passing an
explicit `path` is how tests load a fixture instead of the real corpus.

## `app/search.py` — matching and shaping

Two aliases carry the shapes:

```python
Highlight = dict[str, int | str]   # {"start": int, "end": int, "kind": str}
Payload   = dict[str, Any]         # a JSON object shaped for the response
```

`kind` is one of `"first"`, `"last"`, `"name"` — the client styles each
differently.

### `Name`

`Name.parse(raw)` strips, rejects input with no Hebrew (`ValueError`), and
stores `raw`, `normalized`, `first`, `last`. A multi-word name with no
comma is one name: whitespace is stripped before comparison, so its first
letter comes from the first word and its last from the last word.

`matches_letters(verse)` is the letter-custom predicate.

### Search functions

| Function | Returns |
| --- | --- |
| `letter_highlights(verse)` | Spans for the verse's first and last letters |
| `name_highlights(verse, name)` | A span per occurrence of the name |
| `serialize(verse, highlights=None)` | One verse as a `Payload`, including `rashi`, highlights sorted by `start` |
| `search_name(corpus, name, limit)` | The three result groups for one name |
| `find_pairs(corpus, a, b, gap)` | Verse N matching `a` and verse N+`gap` matching `b` |
| `build_pair_group(corpus, a, b)` | `consecutive` (gap 1), `reversed`, `nearMiss` (gap 2) |
| `search_multi(corpus, names)` | A pair group per unique combination of two names |
| `search(corpus, names, limit)` | The whole response |

Each result group reports `{"total": <all matches>, "verses": [<up to
limit>]}`, so the client can say "showing 10 of 297" without a second
request.

`search_multi` uses `itertools.combinations(..., 2)`: two names give one
group, three give three.

Constants: `DEFAULT_LIMIT = 100`, `MAX_LIMIT = 500`, `MAX_NAMES = 3`,
`PAIR_LIMIT = 50`.

## `app/main.py` — HTTP boundary

### Wiring

`lifespan` loads the corpus at boot and logs the counts. `load_corpus()`
being cached means every later call in a handler is a dict lookup, not a
reload.

The `no_cache_static_assets` middleware forces revalidation:
`static/*.js`/`*.css` have no cache-busting in their URLs, so without it a
returning visitor can be served a stale bundle indefinitely.

**CORS.** `ALLOWED_ORIGINS` is an explicit allowlist (default:
`ot-va-ot.vercel.app` plus localhost), overridable via the environment
without a code change when the frontend moves to a custom domain.
`allow_credentials` stays `False` — there is no auth and nothing for a
credentialed cross-origin request to carry, so a plain allowlist is enough
rather than a stricter per-request check.

### Routes

| Route | Query | Response |
| --- | --- | --- |
| `GET /api/health` | — | `status`, `verses`, `books`, `version`, `source`, `license` |
| `GET /api/search` | `names` (required), `limit` (1..500) | `query`, `names[]`, and `pairs` when ≥2 names |
| `GET /api/random` | `name` (required) | `{"name", "verse"}` — one random letter-match |
| `GET /` + `/static/*` | — | The frontend, same origin |

### Error contract

One shape everywhere, raised as `HTTPException` and rendered by
`http_exception_handler`:

```json
{"error": "<message in Hebrew>", "code": "<stable machine code>"}
```

The `code` values (`empty`, `invalid_name`, `too_many`, `not_found`) are a
contract with `static/i18n.js`, which selects translated text from them.

`parse_names(raw)` splits on `,`، or `;`, drops blanks, and enforces
`MAX_NAMES`.

## `scripts/build_dataset.py` — corpus build

Build-time only; never imported by the running service.

| Function | Contract |
| --- | --- |
| `clean_verse(text)` | Strips parasha markers, resolves ketiv/qere, drops the zero-width joiner — see README "The text is cleaned at build time" for the full case list |
| `clean_rashi_comment(text)` | Strips every HTML tag but a hand-verified `<b>`/`<small>`/`<br>` before the comment is trusted as `innerHTML` client-side |
| `align_rashi(chapters, rashi, book)` | Matches Rashi's per-chapter comments to `chapters` positionally; drops a chapter's Rashi entirely rather than risk attaching a comment to the wrong verse when the chapter boundaries disagree |
| `fetch_book` / `fetch_rashi` | Pull one book's text / Rashi from Sefaria's export, threaded via `ThreadPoolExecutor(max_workers=8)` |
| `main()` | Orchestrates the fetch, validates `BOOK_NAMES_FR` covers every book, writes `data/tanakh.json.gz` |

## Logging

Deliberately minimal: one `print` at boot reporting corpus size. The
service has no users to correlate, no request IDs, and no aggregator to
ship to. Structured logging would be the right call the moment anything
stateful or multi-tenant arrives; today it would be ceremony.

## Test plan

Arrange–Act–Assert throughout, no mocking of the corpus.

| File | Targets |
| --- | --- |
| `tests/test_hebrew.py` | Every primitive, including the ט"ו/ט"ז gematira exception and mark boundaries |
| `tests/test_search.py` | Index correctness, all three match kinds, pair search across chapter boundaries, the cleaned-text regressions, and the HTTP surface via `TestClient` — status codes, the error contract, `limit` clamping |
| `tests/test_build_dataset.py` | `clean_verse()` and `clean_rashi_comment()` against the documented editorial-apparatus cases, without needing the real Sefaria export |

The real dataset loads once per session in `test_search.py`. The trade is a
startup cost for tests that exercise matching against genuine text rather
than a fixture that agrees with the implementation by construction.
