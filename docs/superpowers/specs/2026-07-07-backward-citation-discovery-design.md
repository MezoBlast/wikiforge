# Backward-citation discovery for the explorer skill — design

Date: 2026-07-07
Status: approved (pending spec review)

## Problem

The explorer's citation-chain signal (step 1c in `.forge/skills/explorer/SKILL.md`)
walks `wiki/sources/` bodies for referenced works. By construction it only
discovers papers *older* than what is already ingested. The wiki's domain
(image-edit reward models and benchmarks) moves monthly; the newest frontier is
structurally invisible to bibliography walking. Backward-citation discovery
(cited-by lookup: seed paper → later papers citing it) is the only automated
way to discover forward in time.

## Evidence (probe, 2026-07-07)

Live probe on 4 early seeds (ImagenHub, VIEScore, AURORA, GenAI-Arena):

- **OpenAlex** under-recalls arXiv-native ML badly: 3/0/2/0 cited-by vs
  Semantic Scholar's 76/193/32/79 (~4–13% coverage). Version splits are
  load-bearing (VIEScore's citations sit on a second record). Rejected as
  the recall engine; not worth a fallback (~5% added recall).
- **Semantic Scholar** has full density and merges preprint/published
  records natively (no version-union logic needed). Anonymous pool 429s
  routinely; batch endpoint + backoff works but is unreliable. A free API
  key grants a dedicated ~1 req/sec.
- Precision signal: VIEScore's citer list contains ADIEE (already in the
  wiki — the method retroactively finds in-scope work) plus an
  instruction-editing survey the wiki lacks.

## Design

### 1. API key: bootstrap-provisioned, runtime-gated

`SEMANTIC_SCHOLAR_API_KEY` is provisioned during workspace bootstrap into
`.forge/secrets/credentials.env` (same pattern as `MINERU_API_TOKEN`).
Post-bootstrap, the key is never requested via request-human.

At explorer runtime:
- key present → backward-citation sweep enabled (signal e below)
- key absent → `citations.py` prints `sweep skipped: no
  SEMANTIC_SCHOLAR_API_KEY` and exits 0; explorer records a one-line note
  in its run log and proceeds with signals a–d

### 2. The tool: `.forge/lib/citations.py`

Sibling to `lint.py`. Invocation: `python3 .forge/lib/citations.py --sweep
[--force]`.

Behavior of `--sweep`:
1. **Cadence gate.** No-op (exit 0, note to stdout) if the last sweep in
   the cache is < 14 days old. `--force` overrides.
2. **Seed extraction.** Walk `wiki/sources/*.md`, collect arXiv IDs from
   frontmatter and body `arxiv.org/abs/<id>` URLs.
3. **Citer fetch.** For each seed, page through the S2 Graph API
   `/graph/v1/paper/arXiv:<id>/citations` (fields: `title,year,venue,
   externalIds,citationCount`), throttled to ~1 req/sec, key sent via
   `x-api-key` header.
4. **Co-citing computation.** For each citer, count how many seeds it
   cites. Drop citers already in `wiki/sources/` or already fetched under
   `raw/papers/` (dedup by arXiv ID). Drop citers whose co-citing count
   has not increased since they last appeared in a report (cache lookup) —
   co-citing counts grow as the wiki gains seeds, so a previously
   deferred citer re-surfaces exactly when its priority rises.
5. **Report.** Write `.forge/citations-report.md`: ranked table
   `arXiv ID | title | year | co-citing count | seeds cited`. Citers
   without an arXiv ID are listed in a separate short section (fetch is
   manual for those).
6. **Cache update.** `.forge/citations-cache.json`: map of citer arXiv ID
   → co-citing count at last report, plus last-sweep timestamp. Mutable
   derived state (same category as `.forge/lint-report.md`), not
   append-only.

The script performs no scope judgment, no scoring, no fetching, no
queueing — mechanics only.

### 3. Explorer SKILL.md changes

New **signal (e) — backward-citation sweep** in step 1:
- Run `python3 .forge/lib/citations.py --sweep`, read
  `.forge/citations-report.md`.
- The agent drops out-of-scope candidates (per `wiki/out_of_scope.md`) and
  scores the rest into the unified slate.

Three new scoring-table rows:

| Signal                                   | Score |
| ---------------------------------------- | ----- |
| Cited-by candidate, co-citing ≥ 3        | 50    |
| Cited-by candidate, co-citing = 2        | 30    |
| Cited-by candidate, co-citing = 1        | 10 — usually defer |

Everything downstream is unchanged: planning pass, budget, arXiv fetch
recipe, queue entry format (note e.g. `cited-by sweep; co-cites 3 seeds
(VIEScore, ImagenHub, AURORA)`).

### 4. Failure handling

- 429 despite key → exponential backoff (3 attempts), then give up for
  the run: exit nonzero, leave cache untouched, explorer logs the skip
  and continues. A sweep failure never blocks an explorer run.
- Network failure → same as 429 handling.
- Malformed source page (no arXiv ID) → seed silently skipped; not all
  sources are arXiv papers (repos, web clips).

### 5. Testing

- Run `--sweep --force` against the live wiki seeds; verify ADIEE is
  absent from the report (deduped against `wiki/sources/`) and the
  2026-03 instruction-editing survey surfaces with co-citing ≥ 2.
- Re-run immediately; verify the cadence gate no-ops; re-run with
  `--force` and verify unchanged co-citing counts produce an empty
  report.
- Unset key; verify exit 0 + skip message.

## Out of scope

- OpenAlex fallback or any second citation provider
- Auto-queueing by the script (violates the explorer planning pass)
- Keyless explorer mode (keyless manual runs of the script are not
  supported; the key check is the feature gate)
- Bootstrap-template changes to provision the key (upstream concern;
  this workspace only checks for the key's presence)
