# wikiforge-{{NAME}}

A domain-scoped wiki about **{{NAME}}**, maintained by curator agents and consumed by downstream auto-research agents as a portable bundle.

This is a **curator workspace**. Open it in Obsidian to browse; the agents do the writing.

## To use this repo as a starting point for your own domain

This repo is the canonical wikiforge workspace layout. To start a wiki for a specific domain:

1. Clone or copy the repo and rename it `wikiforge-<your-domain>/` (lowercase, hyphens).
2. Replace the `{{NAME}}`, `{{DATE}}`, `{{AUTHOR}}` placeholders in these files:
   - `README.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `OBSIDIAN.md`
   - `purpose.md`, `wiki/manifest.md`, `wiki/index.md`, `wiki/log.md`, `wiki/out_of_scope.md`
   - `.forge/log.md`
3. Install Python deps: `pip install -r requirements.txt` (just `pyyaml`).
4. `git init` and (if you'll have large PDFs in `raw/papers/`) `git lfs install`.
5. Open in Obsidian and install the Dataview plugin when prompted.
6. Drop sources into `raw/` and invoke the ingest skill — see `.forge/skills/ingest/SKILL.md`.

A one-liner to do the substitution:

```sh
NAME=my-domain DATE=$(date -u +%Y-%m-%d) AUTHOR="$(git config user.name)"
grep -rl '{{NAME}}\|{{DATE}}\|{{AUTHOR}}' . --exclude-dir=.git --exclude-dir=raw \
  | xargs sed -i "s/{{NAME}}/$NAME/g; s/{{DATE}}/$DATE/g; s/{{AUTHOR}}/$AUTHOR/g"
```

## Quick links

- [`purpose.md`](purpose.md) — why this wiki exists
- [`wiki/manifest.md`](wiki/manifest.md) — current scope and top topics
- [`wiki/index.md`](wiki/index.md) — catalog of all pages
- [`schema.md`](schema.md) — page-type spec (load-bearing for agents and curators)
- [`OBSIDIAN.md`](OBSIDIAN.md) — how to view this workspace as an Obsidian vault
- [`AGENTS.md`](AGENTS.md) (= `CLAUDE.md` = `GEMINI.md`) — agent entrypoint

## Working with this wiki

### As a human curator

```sh
# Open in Obsidian (recommended):
open .                              # macOS; or use Obsidian "open folder as vault"

# Inspect health from the command line:
bin/wiki-manifest                   # what's covered
python3 .forge/lib/lint.py --report # what needs attention

# Dashboards in dashboards/ (orphans, stale, low-confidence, by-type, open-requests)
# render as live Dataview tables when opened in Obsidian.
```

### As a curator agent

See `AGENTS.md`. The four skills live under `.forge/skills/`:

- `ingest/`     — raw → wiki
- `query/`      — wiki → answer
- `lint/`       — wiki → report
- `explorer/`   — gap → raw (with `request-human/` for things you can't fetch)

### As a downstream project (consumer)

Build a bundle from this workspace:

```sh
.forge/build.sh --version 0.1.0     # produces dist/{{NAME}}-v0.1.0/
```

Then in any downstream project:

```sh
cp -r dist/{{NAME}}-v0.1.0/ ~/your-project/.claude/skills/{{NAME}}-wiki/
```

The consumer agent reads `SKILL.md` on autoload, calls `bin/wiki-manifest` for orientation, then `bin/wiki-search` / `bin/wiki-read` for queries throughout its work. The bundle requires only POSIX shell — no Python, no dependencies, no install step.

## Layout at a glance

```
.
├── README.md  AGENTS.md  CLAUDE.md  GEMINI.md  OBSIDIAN.md   # entrypoints
├── purpose.md  schema.md  requirements.txt                    # contracts + deps
├── wiki/         # the live, mutable artifact
│   ├── manifest.md  index.md  log.md  out_of_scope.md
│   └── concepts/  conventions/  code-patterns/  claims/  sources/  entities/
├── raw/          # immutable sources — never travels into the bundle
│   └── papers/  repos/  docs/  web/  notes/
├── bin/          # POSIX bash read skill — same source shipped in bundles
│   └── wiki-manifest  wiki-list  wiki-search  wiki-read  wiki-backlinks
├── .forge/       # curator-only machinery — never travels into the bundle
│   ├── build.sh
│   ├── lib/          schema_spec.py  frontmatter.py  wikilinks.py
│   │                 provenance.py   ingest_helpers.py  lint.py  build.py
│   ├── skills/       ingest/  query/  lint/  explorer/  request-human/
│   ├── templates/    SKILL.md.tmpl  MANIFEST.md.tmpl
│   ├── requests/     inbox/  responses/  archive/
│   ├── queue.md  log.md  notify.md
├── .obsidian/    # vault config (graph colors, exclusions, plugin manifest)
├── dashboards/   # Dataview views over wiki/  and  .forge/requests/
└── dist/         # build output (gitignored)
```
