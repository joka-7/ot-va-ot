# Repository structure

Every file in this repo and what is inside it. The tree below is **generated** —
run `python .ai/skills/repo_tree/gen_tree.py --project . --output docs/STRUCTURE.md`
to refresh it, and never edit between the markers by hand.

<!-- BEGIN GENERATED TREE (depth=all entries=all) -->
```text
ot-va-ot/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── security.yml
│   ├── copilot-instructions.md  # AGENTS.md
│   └── dependabot.yml
├── app/
│   ├── corpus.py                # Loading and indexing the Tanakh corpus.
│   ├── hebrew.py                # Hebrew text normalization primitives.
│   ├── main.py                  # FastAPI application.
│   └── search.py                # Verse matching.
├── data/
│   └── tanakh.json.gz
├── docs/
│   ├── HLD.md                   # High-level design — אות ואות
│   ├── LLD.md                   # Low-level design — אות ואות
│   └── STRUCTURE.md             # Repository structure
├── scripts/
│   └── build_dataset.py         # Build the local Tanakh dataset used by the app.
├── static/
│   ├── icons/
│   │   ├── app-icon.png
│   │   ├── apple-touch-icon.png
│   │   ├── icon-192.png
│   │   └── icon-512.png
│   ├── app.js
│   ├── config.js
│   ├── i18n.js
│   ├── index.html
│   ├── manifest.json
│   ├── styles.css
│   └── sw.js
├── tests/
│   ├── test_build_dataset.py    # Tests for the Rashi-alignment logic in scripts/build_dataset.py.
│   ├── test_hebrew.py           # Tests for the Hebrew normalization primitives.
│   └── test_search.py           # Tests for the corpus, the matching logic, and the HTTP API.
├── .ai
├── .gitignore
├── .gitmodules
├── AGENTS.md                    # AGENTS.md
├── CLAUDE.md                    # AGENTS.md
├── Dockerfile
├── GEMINI.md                    # AGENTS.md
├── LICENSE
├── README.md                    # אות ואות — Tanakh verses for a name
├── SECURITY.md                  # Security Policy
├── ai-config.toml
├── pyproject.toml
├── pytest.ini
├── render.yaml
├── requirements-dev.txt
├── requirements.txt
└── vercel.json
```
<!-- END GENERATED TREE -->
