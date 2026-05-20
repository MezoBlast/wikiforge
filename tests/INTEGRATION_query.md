# Integration runbook — query skill

Manual end-to-end check for the curator-side `query` skill and the index it
depends on. Run from a curator workspace with a few ingested pages. The `query`
and `explorer` skills are agent-followed prose, so this is a manual runbook, not
a pytest module.

## Setup

1. Ensure the workspace has at least 3 wiki pages across 2+ page types.
2. Delete `wiki/.meta/` if it exists: `rm -rf wiki/.meta`

## Check 1 — query stops on a missing index

3. As the agent, follow `.forge/skills/query/SKILL.md` step 1: run
   `bin/wiki-manifest`, then `bin/wiki-search <a term>`.
   - EXPECT: `wiki-search` errors with `no .../wiki/.meta/pages.tsv`.
   - EXPECT: the agent stops and reports the index must be refreshed — it does
     NOT write the index itself.

## Check 2 — lint --fix builds the index

4. Run `python3 .forge/lib/lint.py --fix`.
   - EXPECT: output includes `rebuilt .../wiki/.meta`.
   - EXPECT: `wiki/.meta/pages.tsv` and `wiki/.meta/links.tsv` now exist.
5. Run `python3 .forge/lib/lint.py --report`.
   - EXPECT: no `stale-index` warning.

## Check 3 — an answerable query

6. Pick a question the wiki demonstrably covers. Follow the `query` workflow.
   - EXPECT: the answer cites pages by `[[wikilink]]`.
   - EXPECT: no new entry in `.forge/feedback.md`.

## Check 4 — a hard gap is recorded

7. Ask a question on a topic the wiki does not cover. Follow the `query`
   workflow.
   - EXPECT: the agent answers that the wiki has no coverage and does not
     fabricate.
   - EXPECT: `.forge/feedback.md` gains a `query-gap | severity: hard` entry
     with a `Q:` line and an ingest suggestion.

## Check 5 — explorer harvests the gap

8. Follow `.forge/skills/explorer/SKILL.md` step 1.
   - EXPECT: the `query-gap` entry from Check 4 appears as a candidate, scored
     70 (hard).

## Check 6 — stale-index detection

9. Edit any wiki page (e.g. touch its file) without re-indexing.
10. Run `python3 .forge/lib/lint.py --report`.
    - EXPECT: a `[warning] stale-index` line.
11. Run `python3 .forge/lib/lint.py --fix`, then `--report` again.
    - EXPECT: the `stale-index` warning is gone.
