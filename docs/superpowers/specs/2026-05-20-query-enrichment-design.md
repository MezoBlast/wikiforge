# Query Skill Enrichment — Design

> **Status:** approved design, pending implementation plan
> **Date:** 2026-05-20
> **Scope:** the curator-side `query` skill and the machinery it depends on

## Problem

The curator-side `query` skill (`.forge/skills/query/SKILL.md`) is the thinnest of
the five wikiforge skills, and it is currently **inoperable** in the workspace it
is written for. Five gaps:

1. **No curator-side index.** `query`'s workflow runs `bin/wiki-search`,
   `bin/wiki-read`, `bin/wiki-list`, `bin/wiki-backlinks` — all four read
   `wiki/.meta/{pages.tsv,links.tsv}`. The only producer of `.meta/` is
   `build.py`, and it writes it *inside the bundle* (`dist/<name>-vX/wiki/.meta/`),
   never into the curator workspace. In a curator wiki, every command in the
   `query` workflow fails with `no .meta/pages.tsv — run the build`.
2. **The gap → explorer feedback loop is unwired.** `explorer` harvests
   `dist/<latest>/feedback.md` (consumer feedback), but a gap discovered during a
   *curator-side* query has no sink. The skill only says "say so." Design
   constraint 7 names `feedback.md` as an expected append-only curator file; it
   was never created or wired.
3. **Underused read interface.** The skill mentions only `wiki-manifest`,
   `wiki-search`, `wiki-read` — never `wiki-list` or `wiki-backlinks --type`.
4. **Thin relative to siblings.** No worked example/transcript, unlike `ingest`
   and `explorer`.
5. **Incomplete `--type` list.** Lists 3 of the 6 fixed page types.

## Goals

- Make the curator-side `query` workflow actually runnable.
- Close the curator-side query → explorer feedback loop.
- Bring the `query` SKILL.md up to the depth of its siblings.
- Keep `query` a **pure reader** of the wiki — its only write is `.forge/feedback.md`.

## Non-goals / constraints honored

- No `schema_version` bump. The `.meta/` TSV column formats are unchanged.
- Edge-type vocabulary stays at five; page types stay at six.
- Bundle scripts (`bin/wiki-*`) are unchanged — POSIX-only, no new dependencies.
- No new consumer-side behavior; the bundle's `feedback.md` and `SKILL.md.tmpl`
  are untouched.

## Principle: query answers from the wiki, not from memory

The framing principle of the rewritten skill. The `query` skill exists so the
agent grounds its answer in **solid wiki input** — cited pages with provenance —
rather than parametric recall mixed with hallucination. Every step (search, read,
corroborate, cite, record gaps) serves this. An answer the wiki cannot support is
not a `query` answer; it is a feedback entry.

---

## Component A — shared indexer (`.forge/lib/index.py`)

### What it is

A new module that owns the index logic currently inlined in `build.py`. The
`wiki/.meta/` directory is a **wiki artifact** — a derived index of the wiki —
maintained by whoever mutates the wiki.

### Interface

`index.py` exposes:

- `load_pages(wiki_dir)` — moved verbatim from `build.py`; yields
  `(slug, page_type, fm, body)` per page. Unchanged behavior.
- `write_pages_tsv(meta_dir, pages)` — moved from `build.py`.
- `write_links_tsv(meta_dir, pages, kept_slugs)` — moved from `build.py`,
  including its `SystemExit` on an unknown edge type.
- `write_meta(meta_dir, pages)` — convenience: derives `kept_slugs` from `pages`
  and calls both writers.
- `main()` — CLI: `python3 .forge/lib/index.py [--wiki wiki]`. Loads **all**
  pages (no `draft`/`placeholder` filtering — the curator index is complete and
  searches work-in-progress), creates `wiki/.meta/`, writes both TSVs.

### `build.py` refactor

`build.py` gains `import index` and drops its inlined `load_pages`,
`write_pages_tsv`, `write_links_tsv` (~55 lines). It still applies its own
`should_drop` filter and passes the filtered `kept` set to
`index.write_pages_tsv` / `index.write_links_tsv`. Bundle output is
byte-identical to today.

### Who maintains `wiki/.meta/`, and when

| Caller     | When                                          | Pages indexed        |
| ---------- | --------------------------------------------- | -------------------- |
| `ingest`   | Final step of every ingest run                | all (live wiki)      |
| `lint --fix` | On demand — the index-repair path           | all (live wiki)      |
| `build.py` | During a build, into the bundle's `.meta/`    | filtered `kept` set  |

`query` **never** writes the index. `explorer` does not touch it (it never reads
`.meta/`).

---

## Component B — feedback loop (`.forge/feedback.md`)

### The file

A new append-only curator file `.forge/feedback.md` (named in design constraint 7;
never previously created). Seeded with a header by the `bootstrap.md` runbook.
`query` also creates it on first append if absent (crash-safe), mirroring the
hardened ingest queue helpers.

This is distinct from the bundle's `dist/<v>/feedback.md` (consumer-written, free
prose). `.forge/feedback.md` is curator-side and carries structured `query-gap`
entries.

### Entry format

Canonical spec lives in the `query` SKILL.md (writer of record); referenced by
`explorer`. `query` appends a tagged entry when it cannot fully answer:

```
## [2026-05-20T14:03:00Z] query-gap | severity: hard
Q: How does X handle Y?
No page covers this. Suggest ingesting: <topic or source>.

## [2026-05-20T14:07:00Z] query-gap | severity: weak
Q: What is Z?
Answered from [[concepts/z]] (confidence: low). Needs a corroborating source.
```

- `severity: hard` — no wiki page covers the question, or all relevant pages are
  out of scope.
- `severity: weak` — answered, but only from `low`/`placeholder` pages.

### `explorer` integration

`explorer` SKILL.md gains a fourth signal source in step 1: **(d) curator query
gaps** — read `.forge/feedback.md`. New scoring rows:

| Signal                                  | Score |
| ---------------------------------------- | ----- |
| `query-gap severity: hard`               | 70    |
| `query-gap severity: weak`               | 25    |

Rationale: a `hard` gap is a real question the wiki could not answer — same tier
as consumer `feedback.md` (70). A `weak` gap matches "second source for a
low-confidence page" (25). `explorer` dedups entries already named in a prior
`## explorer plan` log block, so a closed gap is not re-proposed indefinitely.

---

## Component C — `query` SKILL.md rewrite

A full rewrite, bringing the skill to sibling depth. Sections:

1. **Framing principle** — "answer from the wiki, not from memory" (above).
2. **Step 1 — Orient.** Run `bin/wiki-manifest`. If `wiki/.meta/` is missing or
   stale, **stop** and tell the agent to run `python3 .forge/lib/lint.py --fix`.
   `query` never writes the index itself.
3. **Step 2 — Search.** `bin/wiki-search`, with the full `--type` enum:
   `concept|convention|code-pattern|claim|source|entity` (singular, matching
   `pages.tsv`).
4. **Read interface section** — documents all five `bin/wiki-*` scripts,
   including `wiki-list` (browse by tag/type/prefix) and
   `wiki-backlinks --type contradicts|supersedes` (the sharp "what disputes this
   claim" tool).
5. **Step — Read & corroborate.** Read candidates; weigh `confidence:`; treat
   typed backlinks as load-bearing; prefer corroborated answers (more than one
   source) and flag single-source answers.
6. **Step — Synthesize.** Cite every claim with the source page's wikilink.
7. **Step — Record the gap.** Replaces the vague "say so": append a `query-gap`
   entry to `.forge/feedback.md` per the format above (hard and weak).
8. **Worked example** — two transcripts: (a) an answerable question end to end
   (`wiki-manifest` → `wiki-search` → `wiki-read` → cited answer); (b) a
   hard-gap question that ends in a `.forge/feedback.md` append.

---

## Cross-cutting documentation & template changes

- **`schema.md`** — its `## Build artifacts` section says the `.meta/` TSVs are
  "regenerated on every build." Reframe to `## Index artifacts`: same TSV format,
  produced by `index.py` — invoked by `build.py` and on demand curator-side
  (`ingest`, `lint --fix`). **No `schema_version` bump.**
- **`lint.py`** — `--fix` additionally regenerates `wiki/.meta/` (via
  `import index`). New mechanical rule **`stale-index`** (warning): fires if
  `wiki/.meta/pages.tsv` is missing, or its mtime is older than the newest
  `*.md` under `wiki/` (excluding `.meta/`).
- **`lint` SKILL.md** — document the `stale-index` rule in the rule table; note
  that `--fix` now also regenerates `.meta/`.
- **`ingest` SKILL.md** — add a final step: regenerate the index with
  `python3 .forge/lib/index.py`.
- **`templates/CLAUDE.md.tmpl` + `templates/AGENTS.md.tmpl`** — add
  `.forge/feedback.md` to the append-only-state rule and the `.forge/` directory
  tree. (`templates/GEMINI.md.tmpl` has no such section — confirm during
  implementation; likely no change.)
- **`templates/.gitignore.tmpl`** — add `wiki/.meta/` (new derived directory; the
  bundle's `.meta/` is already covered by the ignored `dist/`).
- **`bootstrap.md`** — seed `.forge/feedback.md` with a header wherever the
  runbook seeds `.forge/queue.md` / `.forge/log.md`.

---

## Testing

- **`tests/test_index.py`** (new) — round-trip a fixture wiki: assert
  `pages.tsv` / `links.tsv` content; assert the curator CLI indexes `draft:`
  pages while a build-style filtered call excludes them; assert typed
  frontmatter edges win over prose for the same pair.
- **Existing build tests** — must stay green; the `build.py` refactor is
  behavior-preserving for the bundle.
- **lint `stale-index` rule** — a test with an mtime-manipulated fixture
  (index older than a page → warning; index newer → clean; index absent →
  warning).
- **`query` / `explorer` SKILL.md** — skill prose, verified by a manual
  integration runbook in `tests/`, in the style of `tests/INTEGRATION_ingest.md`.

---

## File-change summary

**New:**
- `.forge/lib/index.py`
- `.forge/feedback.md` (seeded per workspace by bootstrap; not in the framework repo)
- `tests/test_index.py`
- `tests/INTEGRATION_query.md` (manual runbook)

**Modified:**
- `.forge/lib/build.py` — import `index`, drop inlined index code
- `.forge/lib/lint.py` — `--fix` regenerates `.meta/`; new `stale-index` rule
- `.forge/skills/query/SKILL.md` — full rewrite
- `.forge/skills/lint/SKILL.md` — `stale-index` rule, `--fix` note
- `.forge/skills/ingest/SKILL.md` — final index-refresh step
- `.forge/skills/explorer/SKILL.md` — fourth signal source, scoring rows
- `schema.md` — `## Build artifacts` → `## Index artifacts`
- `templates/CLAUDE.md.tmpl`, `templates/AGENTS.md.tmpl` — `.forge/feedback.md`
- `templates/.gitignore.tmpl` — `wiki/.meta/`
- `bootstrap.md` — seed `.forge/feedback.md`
