---
name: wikiforge-lint
description: Mechanical health checks for the wiki. Run before any build, after any non-trivial edit, and on demand to triage what needs attention.
---

# lint — wiki health checks

`lint` is mechanical. It does not judge prose, accuracy, or scope — it catches
what a human should never have to hunt for by hand: broken links, malformed
frontmatter, illegal edge types, aging pages, missing excerpts. Its job is to
tell you precisely what to fix and what to triage.

Every run also writes a durable, agent-readable snapshot to
`.forge/lint-report.md`. That file — not the Obsidian `dashboards/` — is the
health view you return to between runs.

## How to invoke

From the workspace root:

```sh
python3 .forge/lib/lint.py --report       # print issues, write the report, exit 0 (default)
python3 .forge/lib/lint.py --strict       # exit non-zero on any BLOCKING error; used by build.sh
python3 .forge/lib/lint.py --fix          # rebuild index.md and wiki/.meta/ from current pages
```

Optional flags:

- `--wiki <dir>` (default `wiki`)
- `--raw <dir>` (default `raw`)
- `--stale-days <N>` (default 180)
- `--rot-days <N>` placeholder rot threshold (default 30)
- `--gap-days <N>` knowledge-gap window shown in the report (default 90)

`--report` and `--strict` regenerate `.forge/lint-report.md`. `--fix` does not —
it is the index-repair path, and it never deletes pages, never mutates
frontmatter, never moves files.

## The report file — `.forge/lint-report.md`

Regenerated in full on every `--report` / `--strict` run. It is a derived
artifact (gitignored), the agent-facing equivalent of the Obsidian `dashboards/`
(which stay for humans browsing in Obsidian). Sections:

- **Errors** — every blocking issue, one line each.
- **Warnings** — grouped by rule code: orphan cohort, stale cohort,
  low-confidence cohort, and so on. Triage by cohort, not page by page.
- **Draft pages** — pages carrying `draft: true`, with their issue counts.
  Their issues never block; they are listed so they are not forgotten.
- **Open knowledge gaps** — `query-gap` entries harvested read-only from
  `.forge/feedback.md` within the last `--gap-days` days. These are questions
  the wiki could not answer — the `explorer` skill turns them into fetch work.

## Reading the stdout output

Each issue is one line:

```
[<severity>] <code>                       <page>: <message>
```

Severity is `error` or `warning`. A blocking error fails `--strict`. An error on
a `draft: true` page is printed with a trailing ` (draft)` and is **not**
blocking. Warnings are always advisory.

The full set of rule codes:

| Code                              | Severity | What it means                                                              |
| --------------------------------- | -------- | -------------------------------------------------------------------------- |
| `broken-wikilink`                 | error    | `[[X]]` does not resolve to a page (or is ambiguous).                       |
| `missing-required-frontmatter`    | error    | A required field per `schema.md` is absent or empty.                       |
| `frontmatter-schema`              | error    | A field value violates its enum or the declared type mismatches its dir.    |
| `duplicate-slug`                  | error    | Same basename used under two different page types.                          |
| `code-pattern-missing-provenance` | error    | code-pattern page missing one or more of repo/commit/path/lines.            |
| `excerpt-missing`                 | error    | code-pattern provenance points at a path not present in `raw/repos/`.       |
| `disallowed-edge-type`            | error    | Page declares an edge type its page type may not emit.                      |
| `claim-without-evidence`          | error    | claim page with both `evidence:` and `counter_evidence:` empty.             |
| `orphan`                          | warning  | Page has no incoming links and is not exempt (sources are exempt).          |
| `stale`                           | warning  | `last_verified` is older than `--stale-days` (default 180).                 |
| `low-confidence`                  | warning  | `confidence:` is `low` or `placeholder` — the page needs a stronger source. |
| `placeholder-rotting`             | warning  | `confidence: placeholder` older than `--rot-days` (default 30).             |
| `superseded-not-stale`            | warning  | A page is named in another's `supersedes:` but still looks fresh.          |
| `contradicts-asymmetric`          | warning  | A `contradicts:` declaration has no matching back-reference on the target. |
| `claim-supports-without-evidence` | warning  | claim has `extends:` but empty `evidence:`.                                 |
| `stale-index`                     | warning  | `wiki/.meta/` or `wiki/index.md` is missing or older than the newest page. |

`low-confidence` and `placeholder-rotting` overlap by design: every
`placeholder` page is `low-confidence`; `placeholder-rotting` flags the *aged*
subset that has gone too long without being filled in.

## Draft pages

`draft: true` in a page's frontmatter means the page is excluded from the build
(`build.py` drops it) — and `lint` honors the same contract. A draft page is
still fully linted, but **all its issues are non-blocking**: they never fail
`--strict`, and they are reported under `## Draft pages` in the report. This is
the real escape hatch: when an error is genuine but you cannot resolve it now,
mark the page `draft: true`, unblock the build, and come back to it.

## What to do after a lint run

1. **Errors first.** Resolve each blocking error by editing the offending page,
   or — if you cannot finish it now — mark it `draft: true`, or move the topic
   to `out_of_scope.md`.
2. **Warnings second.** Open `.forge/lint-report.md` and triage by cohort:
   orphans, then stale, then low-confidence, then the cross-page consistency
   warnings. A long-standing orphan or placeholder may be intentional — judgment,
   not reflex.
3. **Knowledge gaps third.** The report's `## Open knowledge gaps` section is
   what `query` could not answer. You do not fix these in `lint` — `explorer`
   harvests them. Just be aware of what the wiki is missing.
4. **Re-run `lint --strict`** to confirm a clean blocking state before building.

## Worked example

The wiki has a live page with a broken link, an aging page, and one open gap.

```
$ python3 .forge/lib/lint.py --report
[error  ] broken-wikilink                  concepts/attention: unresolved [[concepts/softmaxx]]
[warning] low-confidence                   claims/scaling-laws-hold: confidence is 'low'
[warning] stale                            concepts/dropout: last_verified 2024-10-01 > 180 days ago

1 error(s), 2 warning(s)
```

`.forge/lint-report.md` now contains, among its sections:

```
## Open knowledge gaps

`query-gap` entries from `.forge/feedback.md`, newest first.
- [2026-05-20T14:03:00Z] severity: hard — Q: How does FlashAttention tile the KV cache?
```

You fix the error — the link was a typo for `[[concepts/softmax]]`. You re-verify
`concepts/dropout` against its source and bump `last_verified`. The
`low-confidence` claim and the open gap you leave for `explorer`. Re-run:

```
$ python3 .forge/lib/lint.py --strict
[warning] low-confidence                   claims/scaling-laws-hold: confidence is 'low'

0 error(s), 1 warning(s)
$ echo $?
0
```

Zero blocking errors — the build can proceed.

## What lint does **not** check

- Page quality, prose accuracy, factual correctness.
- Whether sources cited in `evidence:` actually support the claim. (You do that.)
- Whether the wiki's scope as a whole is coherent. (You do that via `purpose.md`
  and `manifest.md`.)
- Style or formatting beyond YAML schema. (No bikeshedding.)
</content>
