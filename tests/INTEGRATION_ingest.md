# Integration test — ingest (PLAN_Init.md Phase 5)

This is the manual test PLAN_Init.md Phase 5 specifies. It cannot run as a unit
test: it needs a bootstrapped domain workspace, network access, and a real
agent invoking the ingest skill. Run it after any change to ingest, normalize,
or the ingest helpers.

## Setup

1. From a fresh clone, run the bootstrap workflow (`bootstrap.md`) to produce an
   initialized workspace. During Step 8, optionally enter a `MINERU_API_TOKEN`.
2. Confirm `.forge/secrets/credentials.env` exists and `.forge/queue.md`,
   `wiki/index.md`, `wiki/log.md` were seeded.

## Test A — ingest a PDF paper

1. Place one arXiv PDF (< 20 pages if no MinerU token) in `raw/papers/`.
2. Invoke the ingest skill: `ingest raw/papers/<file>.pdf`.
3. Verify:
   - `raw/papers/<file>.converted/<file>.md` was created; the original PDF is
     still present and unmodified.
   - `wiki/sources/<slug>.md` exists with valid frontmatter: `content_hash`
     matches `ingest_helpers.content_hash`, `source_type: paper`, `source_path`
     points at the PDF.
   - `wiki/index.md` has a new entry; `wiki/log.md` has an `ingest` line.
   - `python3 .forge/lib/lint.py --report` reports 0 errors.
4. Re-run `ingest` on the same PDF — it must skip (same content hash) and log
   the skip, creating no duplicate page.

## Test B — ingest a repo

1. Clone a small public GitHub repo into
   `raw/repos/<org>/<repo>@<full-sha>/`.
2. Invoke `ingest raw/repos/<org>/<repo>@<sha>`.
3. Verify:
   - A `wiki/sources/<slug>.md` page exists.
   - Any `wiki/code-patterns/<slug>.md` pages carry full provenance
     (`repo`, `commit`, `path`, `lines`, `language`) and the cited file
     resolves under `raw/repos/`.
   - `python3 .forge/lib/lint.py --report` reports 0 errors.

## Test C — ingest a web URL

1. Write a file `raw/web/<name>.url` containing one public URL.
2. Ensure `TAVILY_API_KEY` is set in `.forge/secrets/credentials.env`.
3. Invoke `ingest raw/web/<name>.url`.
4. Verify `raw/web/<name>.converted/<name>.md` was created and a
   `wiki/sources/` page drafted.

## Pass criteria

All three tests produce lint-clean pages with no manual frontmatter fixes, and
the re-run in Test A correctly deduplicates.
