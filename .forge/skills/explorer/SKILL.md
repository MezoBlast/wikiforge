---
name: wikiforge-explorer
description: Identify gaps in the wiki, plan a bounded fetch slate, save publicly-available sources to raw/, queue them for ingest. For non-fetchable sources, invoke request-human.
---

# explorer — gap → raw/

You proactively keep the wiki growing without waiting for the human to point you at sources. You do **not** ingest — you only fetch and queue. Ingest is a separate skill (see `.forge/skills/ingest/SKILL.md`).

The order matters: **read `out_of_scope.md` first, then identify candidates, then plan a bounded slate, then fetch.** Skipping the planning pass turns explorer into a queue-flooding tool that costs ingest cycles you'll regret.

## Workflow

### 0. Honor scope (do this first, every run)

```sh
cat wiki/out_of_scope.md
```

Anything that falls under a listed exclusion is dead to you for this run, even if the lint suite cries for it. If you genuinely think the human's exclusion is wrong, write a note in `.forge/log.md` — do not silently fetch around it.

### 1. Identify candidate sources

Four signal sources, in priority order:

**a) Lint errors and warnings.** Refresh and read the lint report:

```sh
python3 .forge/lib/lint.py --report >/dev/null
cat .forge/lint-report.md
```

Harvest the **mechanical** signals from the report's `## Errors` and
`## Warnings` sections:
- `code-pattern-missing-provenance` / `excerpt-missing` — the cited repo isn't in `raw/repos/`. **High priority** — these are concrete, named gaps.
- `low-confidence` — pages whose `confidence:` is `low` or `placeholder`. Each needs a stronger or second source. **Placeholder pages tagged `stub`** are forward-link stubs ingest created as a "wanted pages" worklist (also listed under the report's `## Placeholder stubs / wanted pages`). Prioritize filling them: if a stub is fillable from sources already in `raw/`/`wiki/sources/`, note it as an ingest follow-up in your run log — you do **not** edit wiki pages or call ingest yourself; if it needs a new source, score it like any `low-confidence` fill.
- `stale` — pages overdue for re-verification against their source.
- `orphan` clusters — may need supporting sources (often LOW priority; an orphan is sometimes just stylistic).

Do **not** harvest the report's `## Open knowledge gaps` section here — those
`query-gap` entries are picked up directly from `.forge/feedback.md` in
signal (d) below. Reading them from both places would double-count.

**b) Consumer feedback.** Read `dist/<latest>/feedback.md` if a built bundle exists. Each entry is a gap a downstream agent actually hit. **Always eligible** regardless of citation count.

**c) Citation chains.** Walk every `wiki/sources/<slug>.md` and collect external references mentioned in the body (cited papers by name/DOI, linked repos, doc URLs). For each candidate target, count how many existing source pages mention it. This count is the **co-citation score**. This pass is the **sole** channel for cited-but-missing sources — ingest deliberately does not pre-queue them, so explorer will not see duplicate candidates.

**d) Curator query gaps.** Read `.forge/feedback.md` if it exists. The `query`
skill appends a `query-gap` entry there whenever the wiki could not answer a
question. Each entry is tagged `severity: hard` (no page covered it) or
`severity: weak` (answered only from `low`/`placeholder` pages). **Always
eligible.** Skip any entry whose question already appears in a prior
`## explorer plan` block in `.forge/log.md` — it has been slated before.

### 2. Plan a bounded slate (do this before any fetch)

For every candidate from step 1, compute a priority score and write it as a checklist to `.forge/log.md` under a new `## explorer plan` heading. The act of writing the plan IS the planning pass — once written, you commit to fetching exactly that slate, nothing more.

**Scoring:**

| Signal                                                                   | Score |
| ------------------------------------------------------------------------ | ----- |
| Closes a `code-pattern-missing-provenance` or `excerpt-missing` error    | 100   |
| Named in consumer `feedback.md`                                          | 70    |
| Named in a `query-gap` entry, `severity: hard`                           | 70    |
| Named in a `query-gap` entry, `severity: weak`                           | 25    |
| Citation-chain target with co-citation score ≥ 3                         | 50    |
| Citation-chain target with co-citation score = 2                         | 30    |
| Citation-chain target with co-citation score = 1                         | 10 — usually defer |
| Adds a second source for a `low-confidence` page                         | 25    |
| Re-verifies a `stale` page against its source                            | 20    |
| Closes an `orphan` warning by adding a supporting source                 | 15    |

**Per-run budget (defaults):**

- ≤ **10** total fetches
- ≤ **3** repos (repos are large; cap them separately)
- ≤ **200 MB** total download size (estimate before fetching; for arxiv, assume ~5 MB unless you know otherwise)

**MinerU ceiling.** ingest normalizes PDFs and Office files through MinerU:
200 MB / 200 pages per file with a `MINERU_API_TOKEN` configured in
`.forge/secrets/credentials.env`, or 10 MB / 20 pages without one. A source
fetched beyond that ceiling will block in the queue (`[!]`) and produce a
request-human entry — so size the slate to what ingest can actually process,
not just to the 200 MB per-run budget above.

Sort candidates by score descending. Take the top-N that fits the budget. **Drop the rest** — they're not gone, they're deferred to the next run, where the priority landscape may have changed.

If you exceed the budget for a documented reason (e.g. a single high-value repo that closes 5 lint errors), record the override in the log entry: `budget overridden: 1 repo > cap because ...`. No silent overrides.

### 3. Fetch the slate

Process the slate one item at a time, in score order. Update `.forge/log.md` after each fetch.

#### arxiv PDF

```sh
arxiv_id="2401.12345"   # may include version, e.g. 2401.12345v2
out="raw/papers/${arxiv_id}.pdf"
curl -sLo "$out" "https://arxiv.org/pdf/${arxiv_id}"
# verify we got a PDF and not an HTML error page
file "$out" | grep -q 'PDF document' || { echo "fetch failed: not a PDF" >&2; rm "$out"; exit 1; }
```

#### Non-arxiv paper

For papers with a direct PDF URL (open-access journal, preprint server, author page):

```sh
out="raw/papers/<first-author>-<year>-<short-title>.pdf"
curl -sLo "$out" "<pdf-url>"
file "$out" | grep -q 'PDF document' || { rm "$out"; exit 1; }
```

If no direct PDF URL exists and the source is behind any kind of paywall or gate, **stop and use the request-human protocol** (step 4). Do not attempt to scrape.

#### GitHub repo

```sh
mkdir -p raw/repos/<org>
git clone --depth=1 https://github.com/<org>/<repo>.git raw/repos/<org>/<repo>-tmp
cd raw/repos/<org>/<repo>-tmp
sha=$(git rev-parse HEAD)
cd ..
mv "$(basename <repo>-tmp)" "<repo>@$sha"
rm -rf "<repo>@$sha/.git"
cd -
```

The `.git/` removal is non-negotiable — the curator workspace does not need every cloned repo's full history, and shipping it bloats backups. The commit sha is the only history we care about, and it's encoded in the directory name.

#### Public doc page or generic web page

The wikiforge curator does not ship an HTML→markdown extractor. Use one of these, in order of preference:

```sh
# Preferred: pandoc if available on the host
url="https://example.com/some/page"
out="raw/docs/<source>-<topic>.md"   # or raw/web/<domain>-<slug>.md for non-doc pages
curl -sL "$url" | pandoc -f html -t markdown_strict --wrap=none -o "$out"

# Fallback A: trafilatura (pip install trafilatura)
python3 -c "import trafilatura; import sys; print(trafilatura.extract(sys.stdin.read()) or '')" \
    < <(curl -sL "$url") > "$out"

# Fallback B: your own tools
# If you (the agent) have a WebFetch / read-URL tool, fetch the page yourself,
# extract the main content by hand, and write the result to $out as plain markdown.
# Prepend a one-line provenance comment so ingest knows the origin:
#   <!-- source: $url, fetched YYYY-MM-DD -->
```

If none of these work, do **not** save raw HTML in place of markdown — that defers parsing to ingest, which is not what ingest is for. Skip the source, log the skip, and submit a request-human entry of type `extraction-tool-needed`.

#### Queue the result

Every successful fetch ends with a queue entry. Use the helper:

```python
from ingest_helpers import append_queue_entry
append_queue_entry(
    ".forge/queue.md",
    "raw/papers/2401.12345.pdf",
    "co-cited 3x; closes excerpt-missing in code-patterns/foo",
)
```

Or hand-edit `.forge/queue.md` directly (it's append-only markdown):

```
- [ ] raw/papers/2401.12345.pdf | co-cited 3x; closes excerpt-missing in code-patterns/foo
```

The note column should record **why** this is in the queue. Ingest reads it for context.

### 4. For non-fetchable sources: request-human

Paywalled papers, private repos, paid datasets, anything requiring credentials — write a request to `.forge/requests/inbox/<id>.md` via the request-human skill. **Always include an `if_denied:` fallback plan.**

```sh
.forge/skills/request-human/submit.sh \
    --agent explorer \
    --type paywalled-paper \
    --urgency useful \
    --key "doi:10.xxxx/yyyy" \
    --title "Smith et al. 2024 (DOI: 10.xxxx/yyyy)" <<'EOF'
## What I need
The paper "Title" (DOI: 10.xxxx/yyyy).

## Why
Co-cited 4x by ingested sources; closes excerpt-missing on code-patterns/bar.

## If granted
Drop the PDF in raw/papers/, queue it.

## If denied
Add a sources/<slug>.md stub with confidence: low and a note pointing at the
DOI for future curators.
EOF
```

See `.forge/skills/request-human/SKILL.md` for full protocol.

### 5. Log your run

Append to `.forge/log.md`:

```
## [YYYY-MM-DDTHH:MM:SSZ] explorer | <N fetched, M queued, K requested, X skipped>

Plan was: <recap top scoring candidates>
Budget: <fetches / repos / total MB>
Overrides: <none | <reason>>
Skipped (with reason): <list>
```

The log is the record of WHY this slate. A future session reads it to understand what's already been considered and rejected, so co-citation scores don't restart at zero.

## Hard rules

- **Does not call ingest.** Ingest reads the queue on its own invocation.
- **Does not delete from `raw/`.** Ingest decides what's a bad source via content_hash; or append a `[!]` blocked entry with a reason.
- **Does not modify wiki pages.** Pages are ingest's territory.
- **Does not fetch what's out of scope.** `wiki/out_of_scope.md` is read at step 0 of every run.
- **Does not exceed the budget without recording the override** in the log entry.
- **Does not fetch outside the committed slate.** New candidates that appear during the run are saved for the next run.

## Naming conventions

- arxiv PDFs: `raw/papers/<arxiv-id>.pdf` (e.g., `2401.12345v2.pdf`) — arxiv id verbatim, including version
- non-arxiv papers: `raw/papers/<first-author>-<year>-<short-title>.pdf` (e.g., `kingma-2015-adam.pdf`)
- repos: `raw/repos/<org>/<repo>@<commit-sha>/` (40-char sha, no truncation)
- docs: `raw/docs/<source>-<topic>.md` (e.g., `pytorch-optimizer-api.md`)
- web: `raw/web/<domain>-<slug>.md` (e.g., `distill-attention.md`)

Naming consistency makes dedup work and makes the queue scannable.

## Parallelism

v1 is sequential. If your slate has 10 fetches, do them one at a time. Sub-agent parallelism is on the v2 list — and even then, the planning pass and the budget stay centralized.
