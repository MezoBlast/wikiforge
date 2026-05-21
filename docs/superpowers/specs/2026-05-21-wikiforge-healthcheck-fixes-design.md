# WikiForge health-check fixes — design

- **Date:** 2026-05-21
- **Status:** approved (design); pending implementation plan
- **Branch:** `fix/healthcheck-2026-05-21` (off `master`)

## Background

A full integration test of the WikiForge pipeline was run against the
`multimodal-llm` domain: a fresh worktree was branched from `master`,
bootstrapped, staged with originals-only raw input (two paper PDFs, one web
HTML, the `tuna-2` repo snapshot), and exercised end to end through
`ingest → query → lint → explorer`. The pipeline ran to completion and the
wiki passed `lint --strict` with 0 errors, but the run surfaced seven defects
in the WikiForge framework. This document specifies the fix for each.

All seven defects are in the **framework** (`bin/`, `.forge/lib/`,
`.forge/skills/`, `templates/`, `bootstrap.md`). Every fix lands on
`fix/healthcheck-2026-05-21` off `master` so that future bootstraps inherit it.
`master` is not modified directly.

## Goals

- Make `bin/wiki-search` usable for agent-driven querying.
- Make MinerU's precision (token) API reachable so real papers can be ingested.
- Remove a cross-skill queue inconsistency and three smaller correctness bugs.

## Non-goals

- No new page types, edge types, or schema changes.
- No embeddings, search index daemon, or any non-POSIX dependency in the
  consumer-facing bundle.
- No change to explorer's fetch-budget *logic* (see Fix 3).
- The MinerU token is a local secret; it is never committed.

## Fixes

### Fix 1 — `bin/wiki-search`: OR-match + ranked retrieval

**Problem.** `bin/wiki-search` lowercases the entire query into one string and
matches it with `grep -i -- "$q"` and awk `index()` — a *contiguous-phrase*
match. A natural-language question phrase, or even a two-word keyword pair with
trivial variance ("fusion strategies" vs "fusion strategy"), almost never
matches verbatim. A query agent following `query/SKILL.md` literally is forced
to guess exact phrasing and call repeatedly, and will wrongly score covered
topics as gaps.

**Change.** Rewrite the matching core, staying pure POSIX `sh` + `awk` + `grep`:

1. Tokenize the query: lowercase, split on whitespace, drop a small stop-word
   list and tokens of length ≤ 2.
2. Match each token independently with `grep -F` (fixed strings — no regex
   metacharacter surprises). A page matches if **any** token hits (OR).
3. Score each page by the count of distinct matched tokens, plus tier bonuses:
   token-in-title outweighs token-in-body; a verbatim whole-phrase hit adds a
   bonus; a slug/filename hit adds a bonus.
4. Sort by score descending, dedup by path, `head -n N`.
5. Keep the `--type` and `--n` flags. Output format keeps `path (source)` plus
   a snippet line; the leading `[rank]` becomes a score.
6. Degenerate case: if every token is a stop-word or ≤ 2 chars, fall back to
   matching the tokens as-is rather than returning nothing.

Single behavior — no phrase/AND mode flag. Ranking already floats multi-token
and phrase matches to the top, which gives precision without extra surface.

**Also.** Rewrite `.forge/skills/query/SKILL.md` so the agent owns keyword
selection: instruct it to extract 3–6 salient keywords from the question, pass
them to `wiki-search`, and read the ranked top-N. Replace the misleading
`wiki-search sparse gradient` worked example with one that reflects OR+ranked
behavior.

**Files.** `bin/wiki-search`, `.forge/skills/query/SKILL.md`.

### Fix 2 — MinerU precision API + cwd-robust credential loading

**Problem.** Both staged paper PDFs failed normalization: one for exceeding the
MinerU free-tier 10 MB limit, one for exceeding the 20-page limit. This blocks
the entire `raw/papers/` ingest path on the free tier.

**Root cause.** `.forge/lib/mineru_api.py` *already* implements the precision
(token) API — `get_mineru_token()` reads `MINERU_API_TOKEN` from the
environment and, when present, routes to `precision_parse()` against
`https://mineru.net/api/v4/file-urls/batch` (200 MB / 200 pp). The token never
arrives because `.forge/lib/credentials.py` defines
`DEFAULT_PATH = ".forge/secrets/credentials.env"` — a **bare relative path**.
`load_credentials()` is called from `normalize.py`, and the ingest skill must
put `.forge/lib/` on the Python path to `import normalize`. If it does so by
running Python with the working directory inside `.forge/lib/`, the relative
path resolves to `.forge/lib/.forge/secrets/credentials.env`, which does not
exist; `load_credentials()` returns `{}` silently and the token is dropped.

**Change.**

1. In `credentials.py`, resolve `DEFAULT_PATH` relative to the module's own
   location: `credentials.py` lives at `<root>/.forge/lib/credentials.py`, so
   the workspace root is `Path(__file__).resolve().parents[2]` and the
   credentials file is `<root>/.forge/secrets/credentials.env`. Keep the
   explicit `path=` override parameter for callers that pass one.
2. Operationally (not committed): place the provided `MINERU_API_TOKEN` into
   the test worktree's `.forge/secrets/credentials.env` (gitignored). Verify a
   real precision-API conversion of a > 10 MB / > 20-page PDF end to end.

`page_range` is intentionally **not** added — the 200-page precision ceiling
makes it unnecessary.

**Files.** `.forge/lib/credentials.py`. (Operational: test worktree
`.forge/secrets/credentials.env`.)

### Fix 3 — explorer / ingest capability alignment

**Problem.** explorer's fetch budget is size-based (≤ 200 MB/run) and
page-unaware. In the test it fetched three papers (Flamingo 31 MB, CLIP ~48 pp,
Tuna 10.7 MB) that the free-tier ingest path cannot process, so explorer fills
a queue ingest cannot drain.

**Resolution.** Closed by Fix 2. With the token, ingest's per-file ceiling
becomes 200 MB / 200 pp, which matches explorer's existing 200 MB per-run
budget. No budget-logic change. Add one paragraph to
`.forge/skills/explorer/SKILL.md`'s budget section stating the MinerU ceiling
(200 MB / 200 pp with a token; 10 MB / 20 pp without) so explorer's fetch
sizing and ingest's capability share one documented mental model.

**Files.** `.forge/skills/explorer/SKILL.md`.

### Fix 4 — bootstrap contract: lint warning on a fresh workspace

**Problem.** `bootstrap.md`'s contract invariant #8 promises
`lint.py --strict` exits 0 with `0 error(s), 0 warning(s)` on the seeded
workspace. It actually emits one `stale-index` warning, because
`wiki/.meta/pages.tsv` is a derived index not built until the first
`lint --fix`. Exit code is still 0, so the gate passes, but the stated text is
wrong.

**Change.** In `bootstrap.md` Step 9, run `python3 .forge/lib/lint.py --fix`
(which builds `wiki/index.md` and `wiki/.meta/`) **before**
`python3 .forge/lib/lint.py --strict`. The strict check then genuinely reports
`0 error(s), 0 warning(s)`, matching invariant #8 and how the ingest skill
closes out.

**Files.** `bootstrap.md`.

### Fix 5 — real timestamps in the operation log

**Problem.** `.forge/skills/request-human/submit.sh` (line ~100) and
`.forge/lib/bootstrap.py` (line ~188) both write `.forge/log.md` entries with a
hardcoded `T00:00:00Z` time component. explorer and query write real ISO-8601
UTC timestamps, so request-human and bootstrap entries sort to a fake midnight
and break intraday log ordering.

**Change.** Replace the hardcoded `T00:00:00Z` with a full UTC timestamp:
`submit.sh` uses `date -u +%Y-%m-%dT%H:%M:%SZ`; `bootstrap.py` uses
`datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.

**Files.** `.forge/skills/request-human/submit.sh`, `.forge/lib/bootstrap.py`.

### Fix 6 — remove the redundant queue channel

**Problem.** The `tuna-2512.02014` paper (Tuna v1) was double-listed in
`.forge/queue.md`: once as a free-text `(not staged) …` note written by
ingest's "surface follow-ups" step, once as a real `raw/papers/2512.02014.pdf`
entry written by explorer after it fetched the same paper via its
citation-chain signal. The two lines carry different first-column "paths", so
no dedup fired. (This is a genuine same-source duplicate, not a Tuna-v1/Tuna-2
confusion — Tuna v1 is `arXiv:2512.02014`, Tuna-2 is `arXiv:2604.24763v2`.)

**Change.** In `.forge/skills/ingest/SKILL.md` Step 9, ingest stops appending
`(not staged)` notes to `.forge/queue.md` for publicly-fetchable cited sources.
explorer's citation-chain signal already discovers cited-but-missing sources by
walking `wiki/sources/` bodies, so the ingest channel is redundant and is the
sole cause of the duplicate. The queue then holds only real `raw/` paths.
Paywalled or credentialed follow-ups still go through the request-human
protocol, unchanged. A one-line note in `explorer/SKILL.md`'s citation-chain
signal confirms it is the single channel for cited-but-missing sources.

**Files.** `.forge/skills/ingest/SKILL.md`, `.forge/skills/explorer/SKILL.md`.

### Fix 7 — gitignore the `.converted/` intermediate

**Problem.** `normalize.py` writes conversion output to a sibling
`<stem>.converted/` directory. This is a regenerable intermediate, but it is
not gitignored, so a successful conversion's output gets committed (the web
source's `.converted/` was committed in the test run).

**Change.** Add `*.converted/` to `templates/.gitignore.tmpl` so every
bootstrapped workspace ignores it. Add the same line to the framework repo's
own `.gitignore` for consistency.

**Trade-off (accepted).** Converted markdown no longer travels with the branch,
so a fresh clone re-converts each source (one MinerU call per paper). This is
acceptable: `.converted/` is a regenerable intermediate, while the durable
curator artifact is the hand-written `wiki/sources/` page. It is consistent
with how other derived artifacts (`wiki/.meta/`, `.forge/lint-report.md`) are
already treated.

**Files.** `templates/.gitignore.tmpl`, `.gitignore`.

## Files touched (summary)

| File | Fix |
| ---- | --- |
| `bin/wiki-search` | 1 |
| `.forge/skills/query/SKILL.md` | 1 |
| `.forge/lib/credentials.py` | 2 |
| `.forge/skills/explorer/SKILL.md` | 3, 6 |
| `bootstrap.md` | 4 |
| `.forge/skills/request-human/submit.sh` | 5 |
| `.forge/lib/bootstrap.py` | 5 |
| `.forge/skills/ingest/SKILL.md` | 6 |
| `templates/.gitignore.tmpl` | 7 |
| `.gitignore` | 7 |

Operational, uncommitted: `MINERU_API_TOKEN` in the test worktree's
`.forge/secrets/credentials.env`.

## Verification

- **Fix 1:** unit-exercise `bin/wiki-search` against the test worktree's wiki —
  multi-word natural-language phrases and single keywords both return ranked,
  relevant pages; `--type` still filters.
- **Fix 2:** with the token in `credentials.env`, re-run ingest on a > 10 MB
  and a > 20-page PDF; both normalize via the precision API and produce
  `wiki/sources/` pages. Confirm `load_credentials()` finds the token when
  Python runs from inside `.forge/lib/`.
- **Fix 4:** a fresh bootstrap ends with `lint --strict` reporting
  `0 error(s), 0 warning(s)`.
- **Fix 5:** new `request-human` and `bootstrap` log entries carry a real
  HH:MM:SS UTC time.
- **Fix 6:** a fresh ingest → explorer cycle produces no duplicate queue entry
  for a cited-but-missing source.
- **Fix 7:** `git status` is clean after a conversion; `.converted/` is
  untracked.
- **Regression:** the full `ingest → query → lint → explorer` pipeline still
  runs end to end and `lint --strict` reports 0 errors.

## Open questions

None — all design forks resolved during brainstorming.
