# Ingest granularity & dense linking — design

- **Date:** 2026-06-16
- **Status:** approved (pending written-spec review)
- **Scope:** live files in this instance; template/master sync deferred (checklist at end)

## Problem

On the first ingest of the Qwen-Image-Bench paper, ingest produced a thin
`sources/` summary that named only ~6 of the paper's 56 taxonomy facets. The user
had to ask twice before the full, count-reconciled taxonomy landed in
`concepts/qwen-image-bench-taxonomy`. That page is the granularity the user wants
by default.

Root cause: the current guidance optimizes for brevity everywhere —
`schema.md` ("keep it brief… aim under ~300 lines"; sources = "one screen of
text, not the full paper") and `.forge/skills/ingest/SKILL.md` ("Not a
paper-summarizer service… not a comprehensive abstract"). That framing
suppresses *structured* extraction, not just verbose narrative. A second goal
also surfaced: the user treats the **inter-page link graph** as a first-class
product ("the ultimate way to an organic structured LLM wiki"), but today a
`[[wikilink]]` to a not-yet-written page is a **hard lint error**, which blocks
forward-linking.

## Goals

1. Ingest extracts **structured content exhaustively** (taxonomies; workflows /
   pipelines such as prompt-construction steps; code structures with their key
   workflows and design ideas; metrics & tabular data; any enumerable schema)
   into dedicated, faithful pages — while keeping **narrative prose concise**.
2. Ingest builds a **densely cross-linked graph**: every page links out and is
   linked to; hub pages exist for recurring metrics/datasets/tools/methods.
3. **Forward-linking is possible** via auto-created `confidence: placeholder`
   stub pages, so dense linking never trips the broken-wikilink error.
4. The new behavior is encoded durably in the shipped files (guidance + one
   helper + a report), not just in one session's memory.

## Non-goals

- No new page types (the 6 are fixed) and no new edge types (the 5 are fixed).
- No new lint **error/warning** rules and no change to `--strict` semantics
  (the report gains a section; severities are unchanged).
- No functional change to `bootstrap.py` (it substitutes templates and makes
  symlinks; behavior lives in the files it ships).
- No heuristic "did you extract everything" checks (rejected as fragile/noisy).

## Design

### 1. The two-axis granularity principle

Replace "keep everything brief" with:

- **Narrative prose → concise.** A `sources/` page stays a curator note: what the
  source contributes, key claims, gaps, suspect parts. Do not recap the paper.
- **Structured content → exhaustive.** Capture enumerable/structured material
  *completely and faithfully* in dedicated typed pages. Reconcile counts/totals;
  cross-check a source's table against its appendix/figures. If a faithful
  reference page exceeds the soft length guidance, **split it into linked pages**
  rather than omitting content.
- **Dense linking is a deliverable.** Every new page should link out and be
  linked to. Create concept/entity hub pages for recurring
  metrics/datasets/tools/methods. Use typed edges
  (`extends`/`contradicts`/`supersedes`/`implements`) only where the source
  establishes them; prose `[[wikilinks]]` everywhere else.

### 2. Placeholder-stub forward-linking

New helper in `.forge/lib/ingest_helpers.py`:

```python
def create_placeholder_stub(slug, title, *, gloss, linked_from,
                            expected_scope=None, source_hint=None,
                            entity_type=None, aliases=None, workspace_root="."):
    """Create wiki/<slug>.md as a *self-describing* confidence:placeholder stub
    if it does not already exist. Idempotent: never overwrites an existing page.
    Returns the slug on creation, None if the page already existed.

    Descriptive by construction: `gloss` (one sentence — what this node IS) and
    `linked_from` (originating page slug(s) + the role the node plays) are
    REQUIRED, so the helper cannot emit a flat "TODO" stub. `expected_scope`
    (what a filled page should cover), `source_hint` (where to source it), and
    `aliases` are optional enrichment.

    Restricted to concept/ and entity/ slugs (the hub types). entity/ slugs
    require entity_type. Raises ValueError for claim/source/code-pattern slugs
    (they need real evidence/provenance and must not be stubbed), for an entity
    slug without entity_type, or for an empty gloss / linked_from.
    """
```

Stub layout (lint-valid on creation; optional lines are omitted when their arg
is absent). The body is a short scaffold — a meaningful node *before* it is
filled — not a flat marker:

```yaml
---
title: <title>
type: concept                # or entity
created: <today>
last_verified: <today>
confidence: placeholder
tags: [stub]
aliases: [<optional alternates>]
# entity stubs only:
entity_type: <person|lab|project|tool|organization>
---

**Stub — needs filling.**

**What it is:** <gloss — one sentence>
**Expected scope:** <expected_scope, if given>
**Linked from:** <linked_from — [[wikilinks]] + the role the node plays>
**Source hint:** <source_hint, if given>
```

The `gloss` is best-effort description at `placeholder` confidence — honest about
being a scaffold, not verified content. Requiring it means the ingesting agent
must understand a node well enough to one-line it before linking, which is the
intended discipline.

Properties (all rely on existing behavior — no new rules):

- `confidence: placeholder` ⇒ **excluded from the built bundle**.
- Existing `placeholder-rotting` (>30 days) and `low-confidence` warnings apply,
  creating fill pressure.
- A stub is created *because* it is being linked to, so it is never orphaned.
- The index builder requires link targets to resolve; the stub makes them
  resolve, so `links.tsv` builds cleanly.

**When to stub:** only for *in-scope* concept/entity nodes you are referencing
but not writing now. Out-of-scope references (e.g. model-catalog names per
`wiki/out_of_scope.md`) stay **plain text** — no stub.

### 3. File-by-file changes

| File | Change |
| --- | --- |
| `schema.md` | Rewrite the Body-conventions section into the two-axis rule; add a short subsection blessing the placeholder-stub forward-link pattern and stating link-density expectations. No type/edge vocabulary changes. |
| `.forge/skills/ingest/SKILL.md` | (a) Rewrite the "not a paper-summarizer / not a code-pasting service" bullets so the brevity rule applies to *narrative* only. (b) Add a "Extract structured content exhaustively" step naming the structured kinds, requiring dedicated pages, count reconciliation, and table-vs-appendix cross-check. (c) Add "Forward-link via self-describing placeholder stubs" pointing at the helper, and require a one-line `gloss` + `linked_from` context whenever a stub is created. (d) Strengthen cross-linking guidance (hub pages; link out *and* in). (e) Add a completeness self-check close-out (scan for un-extracted structures and un-wired links; stub wanted nodes). |
| `.forge/lib/ingest_helpers.py` | Add `create_placeholder_stub()` per §2. |
| `.forge/skills/explorer/SKILL.md` | Name `stub`-tagged placeholder pages explicitly as a fill-worklist alongside the existing `low-confidence` signal. Respect explorer's boundaries: it does **not** edit wiki pages or call ingest — if a stub is fillable from already-ingested `raw/`/`sources/`, it logs an ingest follow-up note in `.forge/log.md` (its existing run-log channel) rather than fetching; if it needs a new source, it scores like a `low-confidence` fill. |
| `.forge/lib/lint.py` | Add a **report-only** "Placeholder stubs / wanted pages" section to `--report` output (and `.forge/lint-report.md`). No new error/warning codes; `--strict` exit behavior unchanged. |
| `CLAUDE.md` | Add one line to the rules encoding the granularity + dense-linking norm, pointing at `schema.md` and the ingest skill. (The "memory line" requested.) |

`docs/refs/ingest.ts` is a reference doc — glance at it during implementation in
case it mirrors ingest guidance, but it is not a primary target.

## Testing

- `tests/test_ingest_helpers.py`: add tests for `create_placeholder_stub` —
  creates a valid concept stub; creates a valid entity stub (with
  `entity_type`); is idempotent (no overwrite, returns None on second call);
  raises for a claim/source/code-pattern slug; raises for an entity slug without
  `entity_type`; **raises for an empty/missing `gloss` or `linked_from`**; the
  rendered stub **contains the gloss and linked-from lines**, and **omits the
  `Expected scope` / `Source hint` lines when those args are absent**. After
  creating stubs, `lint.py` over the temp wiki reports no new **errors**
  (placeholder warnings are expected).
- `tests/test_lint.py`: assert the `--report` output includes the new
  "wanted pages" section when placeholder stubs exist, and that `--strict` still
  exits 0 on an otherwise-clean wiki containing only placeholder stubs (they are
  warnings, not errors).
- Update `tests/INTEGRATION_ingest.md` runbook prose to mention exhaustive
  structured extraction, stubs, and the completeness self-check.
- Gate: `python3 .forge/lib/lint.py --strict` reports 0 errors after all edits.

## Port to master/template (deferred — user will sync)

When syncing the generator, port the edited content to the corresponding
`.tmpl` (or master) copies of:

- `schema.md`
- `.forge/skills/ingest/SKILL.md`
- `.forge/skills/explorer/SKILL.md`
- `.forge/lib/ingest_helpers.py`
- `.forge/lib/lint.py`
- `CLAUDE.md`

`bootstrap.py` itself needs **no change**.

## Resolved decisions

- Granularity rule: exhaustive on structured content + dense linking (not
  "more detail everywhere").
- Forward links: auto-create `confidence: placeholder` stubs (not warning-only
  dangling links, not status-quo hard error).
- Propagation: edit live files now; template sync deferred to the user.
- Enforcement: guidance + one helper + report-only worklist (Approach 1) — no
  mechanical "completeness" checks.
- Stub scope: concept/entity only; out-of-scope refs stay plain text.
- Stub content: **self-describing by construction** — required `gloss` +
  `linked_from`, optional `expected_scope` / `source_hint` / `aliases`. The
  helper cannot emit a flat marker.
