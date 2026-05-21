# Lint Skill Enrichment — Design

> **Status:** approved design, pending implementation plan
> **Date:** 2026-05-21
> **Scope:** the curator-side `lint` skill, `.forge/lib/lint.py`, the index
> module it shares with `build`/`ingest`, and the `explorer` contract it feeds

## Problem

The `lint` engine (`.forge/lib/lint.py`) is sound — all 15 rule codes documented
in `.forge/skills/lint/SKILL.md` are implemented and covered by `tests/test_lint.py`.
The gaps are around **integration and depth** — the same axes the
[query enrichment](2026-05-20-query-enrichment-design.md) fixed for `query`. Six
gaps:

1. **Thinnest SKILL.md of the five skills.** `lint/SKILL.md` is 83 lines vs.
   `ingest` 230, `explorer` 225, `query` 191 (post-rewrite). No worked example /
   transcript — every sibling has one.
2. **No integration runbook.** `ingest` has `tests/INTEGRATION_ingest.md`,
   `query` has `tests/INTEGRATION_query.md`. `lint` has none — its behavior is
   only exercised incidentally inside the `query` runbook (Checks 2 and 6).
3. **Lint warnings have no agent-facing sink, and the skill points agents at
   Obsidian.** Warnings (`orphan`, `stale`, `placeholder-rotting`,
   `superseded-not-stale`, `contradicts-asymmetric`) print to stdout and vanish.
   `SKILL.md` tells the agent to "iterate based on `dashboards/low-confidence.md`
   and `dashboards/orphans.md`" — but those are Obsidian Dataview files, and
   design constraint 9 says agents never touch Obsidian. A non-Obsidian agent has
   nowhere to triage warnings.
4. **The `draft: true` advice is wrong.** `SKILL.md` says "annotate the page with
   `draft: true` to exclude it from the build." But `lint.py` never checks
   `draft` — only `build.py` does (`should_drop`). `lint --strict` (the build
   gate) still fails on a `draft: true` page's errors. The promised escape hatch
   does not exist in the linter.
5. **`index.md` silently drifts — into the bundle.** `lint --fix` rebuilds both
   `index.md` and `wiki/.meta/`. `index.py` (run by `ingest`) rebuilds only
   `.meta/`. `build.py` never regenerates `index.md` at all — it *copies* the
   curator's `wiki/index.md` into the bundle (`SHIPPED_META`). So after an
   `ingest` run, `index.md` is stale, the `stale-index` rule (which checks only
   `.meta/pages.tsv`) does not catch it, and a stale `index.md` ships into the
   bundle.
6. **Broken `explorer` ↔ `lint` contract.** `explorer` step 1(a) and its scoring
   table reference a `low-confidence` lint code. `lint.py` emits no such code —
   `explorer`'s `grep ... low-confidence` over `lint --report` output matches
   nothing today.

## Goals

- Give `lint` an agent-facing, non-Obsidian health sink.
- Make `draft: true` mean the same thing to `lint` as it already does to `build`.
- Stop `index.md` drifting into the bundle.
- Repair the `explorer` ↔ `lint` contract.
- Bring `lint/SKILL.md` to the depth of its siblings.

## Non-goals / constraints honored

- No `schema_version` bump. New lint *rule codes* are not schema-governed
  (`stale-index` was added the same way); page types stay at six, edge types at
  five.
- Bundle scripts (`bin/wiki-*`) are unchanged — POSIX-only, no new dependencies.
- Obsidian stays a curator-side human viewer (constraint 9). `dashboards/*.md`
  are kept for human Obsidian users; the new report is their *agent* equivalent,
  not a replacement.
- `lint` remains a pure reader of the wiki and of `.forge/feedback.md`. Its only
  writes are derived artifacts it owns: `.forge/lint-report.md`, and — via
  `--fix` — `index.md` and `wiki/.meta/`.

## Principle: lint is mechanical, and its output must persist

`lint` does not judge content quality; it reports what is mechanically wrong or
aging. For that output to be *useful* it must outlive the run as something an
agent — not just an Obsidian human — can read. The enrichment's center is a
derived report file that is the single agent-facing health view of the wiki.

---

## Component A — `.forge/lint-report.md`, the agent-facing health snapshot

### What it is

A new **derived** file, overwritten in full by every `lint --report` and
`lint --strict` run. Not append-only state — it is regenerated, like
`wiki/.meta/`. It is gitignored. It is the agent-readable, non-Obsidian
equivalent of `dashboards/` (which stay for human Obsidian users).

`lint --fix` does **not** write the report (it is the index-repair path, not an
inspection run). If `wiki/` is missing the run still errors out as today.

### File location

`.forge/lint-report.md`. `.forge/` already holds curator machinery
(`lib/`, `skills/`) and append-only state (`log.md`, `queue.md`, `feedback.md`);
a derived report is a new category but `.forge/` is its natural home. It is
curator-only and never enters a bundle.

### Structure

```markdown
# Lint report

Generated <ISO-8601 UTC timestamp> · <N> error(s), <M> warning(s)

## Errors

[broken-wikilink] concepts/foo: unresolved [[bar]]
...
_(none)_                       ← when there are no errors

## Warnings

### orphan (3)
- [[concepts/foo]]
...

### stale (2)
- [[concepts/bar]] — last_verified 2025-09-01 (> 180 days)
...

### low-confidence (4)
### placeholder-rotting (1)
### superseded-not-stale (0)        ← omit empty subsections
### contradicts-asymmetric (0)

## Draft pages

Pages with `draft: true` — excluded from the build and from `--strict`. Their
issues are advisory; resolve before un-drafting.
- [[concepts/wip]] — 2 issue(s): broken-wikilink, missing-required-frontmatter
_(none)_

## Open knowledge gaps

`query-gap` entries from `.forge/feedback.md`, last 90 days, newest first.
- [2026-05-20T14:03Z] severity: hard — How does X handle Y? · suggest: <topic>
_(none)_
```

Warning subsections render newest/most-relevant first; empty subsections are
omitted except the section header. Pages are rendered as `[[wikilinks]]` so the
report is navigable.

### The "Open knowledge gaps" fold-in

`lint` reads `.forge/feedback.md` (if it exists), parses `query-gap` entries
(format defined by `query/SKILL.md`), and includes those whose timestamp is
within a recent window. `lint` **never writes** `feedback.md`. If `feedback.md`
is absent the section renders `_(none)_`.

New CLI flag `--gap-days N` (default **90**) controls the window. An entry with
an unparseable or absent timestamp is treated as in-window (shown), so a
malformed entry is surfaced rather than silently dropped.

### New flag summary

- `--gap-days N` (default 90) — knowledge-gap window for the report.

---

## Component B — fix the `draft: true` / `lint --strict` mismatch

`lint.py` learns about `draft: true`:

- A page whose frontmatter has `draft: true` is a **draft page**.
- All issues on a draft page (errors and warnings) are collected as today but
  marked **non-blocking**. They do not count toward the `--strict` non-zero exit.
- Draft-page issues are reported under the report's `## Draft pages` section, and
  in stdout under a `draft` marker, so they are not lost.
- Non-draft pages are unaffected.

Implementation note: `Issue` gains a boolean (e.g. `blocking`, default `True`).
After collecting issues, `lint()` flips `blocking=False` for every issue whose
page is a draft. `--strict` exits non-zero only when a *blocking* error exists.
The stdout error/warning counts and the report distinguish blocking from draft.

This makes `draft: true` mean to `lint` exactly what it already means to
`build.py`'s `should_drop`: the page is excluded from the build gate; finish it
later.

---

## Component C — add the `low-confidence` warning

New warning rule code **`low-confidence`**: fires for any page whose
`confidence` is `low` or `placeholder`. This repairs the `explorer` contract —
`explorer` step 1(a) and its scoring table already treat `low-confidence` as a
lint signal.

`placeholder-rotting` is unchanged and remains the *narrower* escalation: a
`placeholder` page older than `--rot-days`. A placeholder page therefore appears
under both `low-confidence` (always) and `placeholder-rotting` (once aged); this
overlap is intentional and noted in `SKILL.md` — `placeholder-rotting` marks the
urgent subset.

`low-confidence` is a warning (advisory, never blocks `--strict`). It is added to
the `SKILL.md` rule table.

---

## Component D — fix `index.md` drift

### `index.py` owns `index.md`

The `index.md` rendering currently inlined in `lint.fix()` (~40 lines) moves into
`index.py` as `write_index_md(wiki_dir, pages, today)`. `index.py`:

- `write_index_md(wiki_dir, pages, today)` — render `wiki/index.md` from pages,
  grouped by type. Behavior identical to today's `lint.fix()` output.
- `write_meta(meta_dir, pages)` — unchanged.
- `main()` — now writes `wiki/.meta/` **and** `wiki/index.md`.

### Callers

| Caller       | Writes                                  |
| ------------ | --------------------------------------- |
| `index.py` CLI | `wiki/.meta/` + `wiki/index.md` (all pages) |
| `ingest` (final step) | both, via `index.py` CLI       |
| `lint --fix` | both, by delegating to `index` functions |
| `build.py`   | bundle `.meta/` + bundle `index.md` (filtered `kept` set) |

`build.py` gains an `index.write_index_md` call against its filtered `kept`
pages, so the bundle ships a freshly rendered `index.md` instead of copying a
possibly-stale curator `index.md`. `index` is removed from `SHIPPED_META` (it is
generated, not copied); `manifest` and `out_of_scope` remain copied.

### `stale-index` extended

The `stale-index` rule additionally flags `wiki/index.md` when it is missing or
older than the newest `*.md` under `wiki/` (excluding `.meta/`). Same warning
code, same remedy message (`run lint --fix`). The check fires if *either*
`.meta/pages.tsv` *or* `index.md` is stale.

---

## Component E — `lint/SKILL.md` rewrite to sibling depth

Full rewrite to the depth of `ingest`/`query`/`explorer`. Sections:

1. **Framing principle** — lint is mechanical and its output persists in
   `.forge/lint-report.md` (Component A principle).
2. **How to invoke** — the three modes, all flags including `--gap-days`.
3. **The report file** — what `.forge/lint-report.md` is, its sections, that it
   is the agent-facing replacement for the Obsidian `dashboards/`, regenerated
   each run.
4. **Reading the output** — severity, the rule-code table updated with
   `low-confidence`, and a row/paragraph on draft handling.
5. **Draft pages** — how `draft: true` interacts with `lint`: issues advisory,
   listed in the report, never block `--strict`; consistent with `build`.
6. **What to do after a lint run** — errors first, then warnings via the report's
   grouped sections (not Obsidian), then the knowledge-gaps section, then re-run
   `--strict`.
7. **What lint does not check** — unchanged in spirit.
8. **Worked example** — a transcript: a wiki with a broken wikilink, a stale
   page, and an open `query-gap`; show the stdout, show the generated
   `.forge/lint-report.md`, show the agent fixing the error and triaging the
   rest.

The skill stops referencing `dashboards/*.md` as an agent target; it points at
`.forge/lint-report.md`.

---

## Component F — `explorer` integration

`explorer` step 1(a) currently greps `lint --report` stdout. It changes to read
`.forge/lint-report.md`:

- After running `python3 .forge/lib/lint.py --report`, read
  `.forge/lint-report.md` and harvest the **mechanical** signals from its
  `## Errors` and `## Warnings` sections: `code-pattern-missing-provenance`,
  `excerpt-missing`, `low-confidence` (now a real code), `orphan`,
  `stale`, `placeholder-rotting`.
- `explorer` continues to harvest `query-gap` entries from `.forge/feedback.md`
  directly (step 1(d), unchanged). It does **not** read the report's
  `## Open knowledge gaps` section — that section is for the triaging agent;
  harvesting it too would double-count gaps.

Scoring-table **values are unchanged**. The `low-confidence` row already exists
(score 25); it now actually matches a signal. A one-line note is added clarifying
that lint signals come from `.forge/lint-report.md` and gaps from `feedback.md`.

---

## Cross-cutting documentation & template changes

- **`templates/.gitignore.tmpl`** — add `.forge/lint-report.md` (derived,
  regenerated each run).
- **`templates/CLAUDE.md.tmpl` + `templates/AGENTS.md.tmpl`** — add
  `.forge/lint-report.md` to the `.forge/` directory tree, marked *derived* (NOT
  added to the append-only-state rule — it is overwritten, not appended).
  Confirm `GEMINI.md.tmpl` during implementation; likely a parallel tree edit or
  no change.
- **`schema.md`** — its `## Index artifacts` section: note `index.py` now also
  owns `wiki/index.md` (produced curator-side by `ingest` / `lint --fix` and into
  the bundle by `build.py`). No `schema_version` bump.
- **`ingest/SKILL.md`** — minor: its close-out `lint --report` now also writes
  `.forge/lint-report.md`; its `index.py` step now also refreshes `index.md`.
- **`bootstrap.md`** — no new seeding required (`lint-report.md` is generated on
  first lint run; `feedback.md` seeding already exists from the query
  enrichment). Confirm during implementation.

---

## Testing

- **`tests/test_lint.py`** (extend):
  - draft pages — a `draft: true` page with a broken wikilink: `--strict`-style
    blocking-error count is 0; the issue is still present and marked
    non-blocking.
  - report file — after a `--report`-style run, `.forge/lint-report.md` exists
    with the `## Errors`, `## Warnings`, `## Draft pages`, `## Open knowledge
    gaps` sections; counts match.
  - `low-confidence` — a `confidence: low` page yields a `low-confidence`
    warning; a fresh placeholder yields `low-confidence` but not
    `placeholder-rotting`.
  - knowledge-gap window — a `feedback.md` with one in-window and one
    out-of-window `query-gap`: only the in-window entry appears in the report.
  - `stale-index` on `index.md` — an mtime-manipulated fixture where
    `.meta/pages.tsv` is fresh but `index.md` is older than a page → warning;
    both fresh → clean.
- **`tests/test_index.py`** (extend) — `index.py` CLI / `write_index_md` writes
  `wiki/index.md` with the expected grouped content; round-trips with the
  existing `.meta/` assertions.
- **Existing tests** — `test_lint.py` `fix` tests and all `build` tests stay
  green; the `index.md` move and `build.py` change are behavior-preserving for
  the rendered output.
- **`tests/INTEGRATION_lint.md`** (new) — manual runbook in the style of
  `tests/INTEGRATION_query.md`: clean wiki → 0 errors + report written; broken
  wikilink → error + `--strict` non-zero + report `## Errors`; mark that page
  `draft: true` → `--strict` zero + page under `## Draft pages`; stale page →
  `## Warnings` `stale`; `confidence: low` page → `low-confidence`; seed an
  in-window and an out-of-window `query-gap` → only in-window under `## Open
  knowledge gaps`; `explorer` reads `.forge/lint-report.md` and picks up the
  mechanical signals; `index.md` drift → run `index.py`, confirm `index.md`
  refreshed and `stale-index` clears.

---

## File-change summary

**New:**
- `.forge/lint-report.md` (derived per workspace; not in the framework repo)
- `tests/INTEGRATION_lint.md` (manual runbook)

**Modified:**
- `.forge/lib/lint.py` — write `.forge/lint-report.md`; `draft` non-blocking
  reclassification; `low-confidence` rule; `stale-index` also checks `index.md`;
  `--gap-days` flag; `fix()` delegates `index.md` to `index`
- `.forge/lib/index.py` — `write_index_md`; `main()` writes `index.md` too
- `.forge/lib/build.py` — render bundle `index.md` via `index.write_index_md`;
  drop `index` from `SHIPPED_META`
- `.forge/skills/lint/SKILL.md` — full rewrite
- `.forge/skills/explorer/SKILL.md` — read `.forge/lint-report.md`; contract note
- `.forge/skills/ingest/SKILL.md` — close-out notes
- `schema.md` — `## Index artifacts` note
- `templates/.gitignore.tmpl` — `.forge/lint-report.md`
- `templates/CLAUDE.md.tmpl`, `templates/AGENTS.md.tmpl` — `.forge/` tree
- `tests/test_lint.py`, `tests/test_index.py` — new cases
</content>
</invoke>
