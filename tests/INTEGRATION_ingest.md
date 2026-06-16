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

## Scenario: Oversize PDF fallback (agent self-extract)

**Setup:**
1. Start from a freshly bootstrapped workspace with no MINERU_API_TOKEN
   configured — the seeded `.forge/secrets/credentials.env` has the
   `# MINERU_API_TOKEN=` line commented out.
2. Place an arxiv PDF larger than 10 MB at `raw/papers/<id>.pdf`. The MMMU
   paper at 17 MB is a representative case:
   `curl -sLo raw/papers/2311.16502.pdf https://arxiv.org/pdf/2311.16502.pdf`.
3. Invoke `ingest raw/papers/<id>.pdf`.

**Expected — Continue path (interactive):**

- `normalize_source` raises NormalizeError; the agent calls
  `agent_extract_advice` and gets `(True, "pdf-read", "<size> MB > 10 MB ...; no MINERU_API_TOKEN")`.
- The agent reads the PDF paginated and writes
  `raw/papers/<id>.converted/<id>.md`. Its first line is
  `<!-- converted: agent-extracted fallback (pdf-read, reason: ...), <date> -->`.
- The agent prompts: "<file> exceeded MinerU's free tier; I self-extracted
  it. Continue, or provide a MINERU_API_TOKEN to retry with MinerU?".
- User picks **Continue**.
- The queue entry advances to `[x]`; `wiki/sources/<slug>.md` is drafted
  normally.
- `python3 .forge/lib/lint.py --strict` exits 0.

**Expected — Provide-token path (interactive):**

- Same setup; user picks **Provide a MINERU_API_TOKEN** and pastes a token.
- Agent calls `credentials.set_credential("MINERU_API_TOKEN", <value>)`;
  `.forge/secrets/credentials.env` now carries an uncommented
  `MINERU_API_TOKEN=<value>` line (verify the key by name; never paste a real
  token into this runbook).
- Agent re-calls `normalize_source(path, force=True)`; MinerU overwrites
  `raw/papers/<id>.converted/<id>.md`. Its first line is now MinerU's own
  output, not the agent-extracted provenance header.
- Queue entry `[x]`; lint exits 0.

**Expected — Headless path (no interactive prompt available):**

- Same setup; the agent runtime has no way to prompt the user.
- The agent does NOT prompt. It keeps the self-extracted conversion.
- `.forge/log.md` carries one new line:
  `## [<UTC>] ingest | self-extracted <path> (pdf-read, reason: ...); configure MINERU_API_TOKEN for higher-fidelity conversion`.
- Queue entry `[x]`; lint exits 0.

**Negative case — `.xls` legacy file:**

- Drop a `.xls` file in `raw/docs/`. `normalize_source` raises NormalizeError;
  `agent_extract_advice` returns `(False, "none", "legacy OLE binary, ...")`.
- The queue entry is set to `[!]`; a `request-human` entry of type
  `large-download` is written to `.forge/requests/inbox/`. No `.converted/`
  is produced. Lint exits 0 (the source is blocked, not corrupt).

**Negative case — `.url` fetch failure (Tavily unavailable):**

- Drop a `raw/web/example.url` whose single line is a URL, with no `TAVILY_API_KEY`
  configured (or with the `tvly` CLI uninstalled). `normalize_source` raises
  `NormalizeError`; `agent_extract_advice` returns
  `(False, "none", "Tavily fetch failure; URL retrieval cannot be self-handled")`.
- Queue entry is set to `[!]`; a `request-human` entry of `type: paid-api`
  is written to `.forge/requests/inbox/`. No `.converted/` is produced.
  Lint exits 0.

## Scenario: structured extraction + placeholder stubs

**Setup:** ingest a paper containing a multi-level taxonomy or a large
criteria/metrics table (the Qwen-Image-Bench paper is a representative case).

**Expected:**

- A dedicated `concepts/<slug>-taxonomy` (or equivalent) page enumerates the
  structure **completely** — counts reconcile with any total the source states
  (e.g. a "56 facets" claim yields 56 enumerated facets). The `sources/` page
  stays a brief prose note that links to it.
- Forward references to not-yet-written concepts/entities resolve because ingest
  created `confidence: placeholder` stubs (tagged `stub`) via
  `ingest_helpers.create_placeholder_stub`. Each stub carries a one-line
  *What it is* gloss and a *Linked from* context line; none is a flat marker.
- `python3 .forge/lib/lint.py --strict` exits 0, and `--report` lists the new
  stubs under `## Placeholder stubs / wanted pages`.
- Out-of-scope references (e.g. evaluated model names) appear as plain text, not
  stubs.
