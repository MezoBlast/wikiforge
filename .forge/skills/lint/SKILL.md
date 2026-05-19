---
name: wikiforge-lint
description: Mechanical health checks for the wiki. Run before any build, after any non-trivial edit, and on demand to triage what needs attention.
---

# lint — wiki health checks

You are linting the wiki. The linter is mechanical; it does not judge content quality. It catches:

- Broken or ambiguous `[[wikilinks]]`
- Missing or malformed frontmatter
- Disallowed or unknown edge types
- Orphan pages (warning)
- Stale or rotting pages (warning)
- Code-pattern pages whose provenance does not resolve in `raw/repos/`
- Claims with no evidence on either side
- Cross-page inconsistencies (superseded-but-still-fresh, asymmetric contradicts, etc.)

## How to invoke

From the workspace root:

```sh
python3 .forge/lib/lint.py --report       # print issues, exit 0 (default)
python3 .forge/lib/lint.py --strict       # exit non-zero on any error; used by build.sh
python3 .forge/lib/lint.py --fix          # rebuild index.md from current pages
```

Optional flags:

- `--wiki <dir>` (default `wiki`)
- `--raw <dir>` (default `raw`)
- `--stale-days <N>` (default 180)
- `--rot-days <N>` placeholder rot threshold (default 30)

## Reading the output

Each issue is one line:

```
[<severity>] <code>                       <page>: <message>
```

Severity is `error` or `warning`. Errors block `--strict`. Warnings are informational.

The full set of rule codes:

| Code                              | Severity | What it means                                                              |
| --------------------------------- | -------- | -------------------------------------------------------------------------- |
| `broken-wikilink`                 | error    | `[[X]]` does not resolve to a page (or is ambiguous).                       |
| `missing-required-frontmatter`    | error    | A required field per `schema.md` is absent or empty.                       |
| `frontmatter-schema`              | error    | A field value violates its enum or the declared type mismatches its dir.    |
| `duplicate-slug`                  | error    | Same basename used under two different page types.                          |
| `code-pattern-missing-provenance` | error    | code-pattern page missing one or more of repo/commit/path/lines.            |
| `excerpt-missing`                 | error    | code-pattern provenance points at a path not present in `raw/repos/`.       |
| `disallowed-edge-type`            | error    | Page declares an edge type its page type may not emit (e.g. concept `supersedes:`). |
| `claim-without-evidence`          | error    | claim page with both `evidence:` and `counter_evidence:` empty.             |
| `orphan`                          | warning  | Page has no incoming links and is not exempt (sources are exempt).          |
| `stale`                           | warning  | `last_verified` is older than `--stale-days` (default 180).                 |
| `placeholder-rotting`             | warning  | `confidence: placeholder` older than `--rot-days` (default 30).             |
| `superseded-not-stale`            | warning  | A page is named in another's `supersedes:` but still looks fresh.          |
| `contradicts-asymmetric`          | warning  | A `contradicts:` declaration has no matching back-reference on the target. |
| `claim-supports-without-evidence` | warning  | claim has `extends:` but empty `evidence:`.                                 |

## Decisions, not rules

- Errors block the build. Fix them or annotate the page with `draft: true` to exclude it from the build (and then come back to it).
- Warnings are advisory. A long-standing `placeholder` or `orphan` may be intentional — for those, you'll iterate based on `dashboards/low-confidence.md` and `dashboards/orphans.md`, not by chasing every lint warning.
- `--fix` is conservative: it rebuilds `index.md` from the current page set. It does not delete pages, does not silently mutate frontmatter, and does not move files.

## What to do after a lint run

1. Errors first. Resolve each by editing the offending page or `out_of_scope.md`.
2. Warnings second. Triage in batches — look at `orphan` cohorts, then `stale` cohorts, then the cross-page consistency warnings.
3. Re-run `lint --strict` to confirm clean state before building.

## What lint does **not** check

- Page quality, prose accuracy, factual correctness.
- Whether sources cited in `evidence:` actually support the claim. (You do that.)
- Whether the wiki's scope as a whole is coherent. (You do that via `purpose.md` and `manifest.md`.)
- Style or formatting beyond YAML schema. (No bikeshedding.)
