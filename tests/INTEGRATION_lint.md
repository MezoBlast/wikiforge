# Integration runbook — lint skill

Manual end-to-end check for the curator-side `lint` skill: the report file,
draft handling, the `low-confidence` rule, the knowledge-gap fold-in, and
`index.md` consistency. Run from a curator workspace with a few ingested pages.

## Setup

1. Ensure the workspace has at least 3 wiki pages across 2+ page types.
2. Run `python3 .forge/lib/lint.py --fix` so the index starts fresh.

## Check 1 — a clean run writes the report

3. Run `python3 .forge/lib/lint.py --report`.
   - EXPECT: exit code 0.
   - EXPECT: `.forge/lint-report.md` exists, with `## Errors`, `## Warnings`,
     `## Draft pages`, `## Open knowledge gaps` sections.

## Check 2 — a broken wikilink blocks --strict

4. Edit any page to add a `[[concepts/does-not-exist]]` link.
5. Run `python3 .forge/lib/lint.py --strict`; check `echo $?`.
   - EXPECT: a `[error] broken-wikilink` line and a non-zero exit code.
   - EXPECT: the error appears under `## Errors` in `.forge/lint-report.md`.

## Check 3 — draft:true unblocks the page

6. Add `draft: true` to that page's frontmatter.
7. Run `python3 .forge/lib/lint.py --strict`; check `echo $?`.
   - EXPECT: exit code 0 — the error is now non-blocking.
   - EXPECT: the page appears under `## Draft pages` in the report, not
     `## Errors`.
8. Revert the broken link and the `draft: true` line.

## Check 4 — low-confidence warning

9. Set a page's `confidence:` to `low`. Run `python3 .forge/lib/lint.py --report`.
   - EXPECT: a `[warning] low-confidence` line; the page under the
     `### low-confidence` cohort in the report.
10. Revert the confidence change.

## Check 5 — knowledge gaps fold in from feedback.md

11. Append a `query-gap` entry to `.forge/feedback.md` dated today:
    `## [<today>T12:00:00Z] query-gap | severity: hard` then a `Q:` line.
12. Run `python3 .forge/lib/lint.py --report`.
    - EXPECT: the entry appears under `## Open knowledge gaps`.
13. Append a second `query-gap` dated more than 90 days ago and re-run.
    - EXPECT: the old entry does NOT appear (outside the `--gap-days` window).

## Check 6 — explorer reads the report

14. Follow `.forge/skills/explorer/SKILL.md` step 1(a).
    - EXPECT: the agent runs `lint --report` and reads `.forge/lint-report.md`
      for mechanical signals — it does not re-harvest the gap section.

## Check 7 — index.md stays consistent

15. Edit any wiki page, then run `python3 .forge/lib/lint.py --report`.
    - EXPECT: a `[warning] stale-index` line (page newer than the index).
16. Run `python3 .forge/lib/index.py`, then `python3 .forge/lib/lint.py --report`.
    - EXPECT: no `stale-index` warning — `index.py` refreshed both `index.md`
      and `wiki/.meta/`.
</content>
