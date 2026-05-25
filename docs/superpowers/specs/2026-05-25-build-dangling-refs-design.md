# Build-time dangling-ref handling — design

- **Date:** 2026-05-25
- **Status:** approved (design); pending implementation plan
- **Branch:** TBD (off `master`)

## Background

The bundle builder (`.forge/lib/build.py`) drops `confidence: placeholder` and
`draft: true` pages by default before writing `dist/<name>-v<version>/`. Page
bodies are then copied verbatim via `FM.dump(fm, body)`. The drop pass does
not inspect prose `[[wikilinks]]` and `index.write_links_tsv` silently filters
unresolved targets out of `.meta/links.tsv`, so the meta file looks clean even
when prose references survive into the bundle pointing at slugs that were
dropped.

Surfaced by the multimodal-llm fixture's Q3 ("How does CLIP loss relate to
contrastive pretraining for multimodal models?"):

- The curator workspace had `concepts/clip` and `concepts/clip-loss` as
  `confidence: placeholder` stubs whose body documented the gap and named the
  citation needed to close it (Radford et al. 2021, arxiv:2103.00020).
- The build dropped both stubs, leaving five prose `[[concepts/clip]]` and
  `[[concepts/clip-loss]]` references in `entities/llava`,
  `sources/tuna-2-paper`, `sources/llava-visual-instruction-tuning`, and
  `concepts/encoder-free-multimodal`.
- A consumer agent following any of those wikilinks via `bin/wiki-read` gets
  a hard error (`wiki-read: no page at .../concepts/clip-loss.md`) and no
  breadcrumb explaining that the gap is *known*.

The fix has two layers:

1. **Design layer** — placeholder pages are load-bearing for the gap-marker
   UX and should ship by default. Their `confidence: placeholder` value
   already encodes "known gap"; the consumer skill teaches consumers how to
   interpret that.
2. **Safety layer** — after any future page drop (drafts today, placeholders
   under opt-in, future excludes), the build must reject prose or
   frontmatter references to dropped slugs. Silent filtering of dangling
   typed edges in `links.tsv` is retired in favour of the same hard check.

## Goals

- Bundles preserve the curator's intentional "known gap" stubs unless a
  caller explicitly opts into stripping them.
- A bundle can never ship with a prose `[[wikilink]]` or frontmatter typed
  edge pointing at a slug that is not in `wiki/.meta/pages.tsv`. The build
  fails fast with a precise diagnostic when this would happen.
- The check covers every current and future drop rule with a single helper —
  no per-rule code path.
- Consumer agents have a documented contract for reading `confidence:
  placeholder` pages.

## Non-goals

- No change to the SKILL.md template's other sections (top topics,
  feedback channel, edge-type vocabulary). Those are findings #3 and #4 from
  the Q3 comparison and are out of scope for this spec.
- No change to the curator-side `.forge/skills/query` workflow. The fix is
  in the build layer; the curator-side query already correctly resolves
  placeholder pages because they exist in `wiki/`.
- No change to the bundle's `feedback.md` (still consumer-→curator only).
- No new wikilink syntax or schema fields. The fix uses existing
  `wikilinks.extract_prose_links` and `wikilinks.extract_frontmatter_edges`.

## Behaviour change

### `build.py` argparse

Before (current):

```
--keep-placeholders     include pages with confidence: placeholder
                        (default: drop)
```

After:

```
--drop-placeholders     drop pages with confidence: placeholder
                        (default: keep — placeholders are known-gap markers)
```

The `--keep-placeholders` flag is removed (no aliases, no deprecation
warning — wikiforge has no external callers yet that would break).

`build()`'s `drop_placeholder` parameter inverts: callers pass
`drop_placeholder=False` by default.

### `should_drop`

Logic unchanged. Only the default value flowing into it changes.

## Safety layer: dangling-ref validation

### New helper

A single function added to `build.py` (or a new `dangling_refs.py` if the
implementation plan calls for it — leave to plan writer):

```python
def validate_no_dangling_refs(kept_pages, kept_slugs):
    """Raise SystemExit with a precise diagnostic if any kept page has a
    prose [[wikilink]] or frontmatter typed-edge pointing at a slug not in
    kept_slugs. Diagnostics are emitted in deterministic order
    (sorted by (from_slug, source, target))."""
```

Implementation uses existing helpers:

- `wikilinks.extract_prose_links(body)` for prose `[[X]]` occurrences.
- `wikilinks.extract_frontmatter_edges(fm)` for typed-edge targets.
- `wikilinks.normalize_target` + `wikilinks.resolve` against `kept_slugs`
  (plus the basename-shorthand index that `write_links_tsv` already builds).

A reference is *dangling* iff `resolve(target, kept_slugs, basename_index)`
returns `None`. The check skips refs inside HTML comments
(`extract_prose_links` already strips them).

### Call site

In `build()`, between the `kept` computation (line 122) and the first write
to `out_wiki` (line 127):

```
kept = [p for p in all_pages if not should_drop(...)]
kept_slugs = {slug for slug, pt, _, _ in kept if pt is not None}
validate_no_dangling_refs(kept, kept_slugs)
```

Failure aborts the build before any file is written to `dist/`. No partial
bundle is ever produced.

### Diagnostic format

One line per dangling reference, written to stderr. Format:

```
dangling-ref: <from-slug>  <source>  -->  [[<target>]]
```

Where `<source>` is either `body` (for a prose link) or
`frontmatter:<edge>` (for a typed edge, e.g. `frontmatter:extends`).

Example output for the multimodal-llm fixture under
`build.py --drop-placeholders`:

```
dangling-ref: concepts/encoder-free-multimodal             body  -->  [[concepts/clip-loss]]
dangling-ref: entities/llava                               body  -->  [[concepts/clip]]
dangling-ref: sources/llava-visual-instruction-tuning      body  -->  [[concepts/clip]]
dangling-ref: sources/llava-visual-instruction-tuning      body  -->  [[concepts/clip-loss]]
dangling-ref: sources/tuna-2-paper                         body  -->  [[concepts/clip]]
build aborted: 5 dangling reference(s)
```

Exit code is non-zero (use `SystemExit(f"build aborted: {n} dangling reference(s)")`).
Process exits after listing *all* dangling refs — not the first — so the
curator can fix them in one pass.

### `index.write_links_tsv` cleanup

Currently `write_links_tsv` silently filters dangling targets out of
`.meta/links.tsv` (the `if resolved: typed[...] = edge` and
`if resolved: prose.add(...)` branches). After the safety check above, no
dangling ref can reach `write_links_tsv` — the filter is dead code.

Tighten `write_links_tsv` to **assert** rather than silently filter: if a
target fails to resolve, raise `RuntimeError(f"internal: unresolved target
{target!r} from {slug!r} reached write_links_tsv; validate_no_dangling_refs
should have caught this")`. This is defensive — the check is the contract.

## SKILL.md template update

`.forge/templates/SKILL.md.tmpl` gets one new paragraph, inserted after the
"How to use" section, before "When to use this wiki vs. live retrieval":

> ## Known gaps
>
> Some pages ship with `confidence: placeholder`. These are **known gaps**:
> the curator has noted the topic is referenced by other pages but the
> canonical source has not yet been ingested. Read the stub for the citation
> hint — it names the paper, repo, or URL that would close the gap — then
> fall back to live retrieval. Do not treat placeholder content as
> authoritative.

No other template change.

## Tests

### Unit test — `tests/test_build_dangling.py` (new file)

`test_validate_no_dangling_refs_passes_on_clean_set`: synthetic
`(kept_pages, kept_slugs)` where every prose and typed-edge target resolves.
Function returns `None`, no `SystemExit`.

`test_validate_no_dangling_refs_catches_prose_link`: one page body contains
`[[missing-slug]]`. `SystemExit` raised; diagnostic on stderr contains the
from-slug, `body`, and `[[missing-slug]]`.

`test_validate_no_dangling_refs_catches_typed_edge`: one page frontmatter has
`extends: [missing-slug]`. `SystemExit` raised; diagnostic contains
`frontmatter:extends` and `[[missing-slug]]`.

`test_validate_no_dangling_refs_reports_all_failures`: multiple dangling refs
across multiple pages. Diagnostic contains *all* of them in sorted order;
exit message reports the total count.

`test_validate_no_dangling_refs_resolves_via_basename`: target uses basename
shorthand (`[[clip]]` resolving to `concepts/clip`) and the page exists.
No error.

`test_validate_no_dangling_refs_skips_html_comments`: page body contains
`<!-- [[ignored]] -->`. No error even if `ignored` is not in `kept_slugs`.

### Integration test — `tests/INTEGRATION_build.md` (new file)

A runbook (matching the style of the existing
`tests/INTEGRATION_ingest.md`) that:

1. Bootstraps a synthetic 3-page workspace (one placeholder page; one page
   referencing it in prose; one unrelated page).
2. Runs `python3 .forge/lib/build.py --workspace . --version 0.0.1`
   (default args). Expects success — placeholder ships, ref resolves.
3. Runs `python3 .forge/lib/build.py --workspace . --version 0.0.2
   --drop-placeholders`. Expects non-zero exit, `dangling-ref:` line on
   stderr, no `dist/<name>-v0.0.2/` directory created.
4. Repeats step 3 after the curator removes the offending prose ref.
   Expects success.

### Regression coverage

The existing multimodal-llm fixture (`dev-tools/fixtures/multimodal-llm`)
becomes an implicit regression test: a default-args bundle of that fixture
now contains 20 pages (was 18) and no dangling refs. The fixture's
`expectations.md` should be updated to reflect the new count (out of scope
for *this* spec but should be flagged in the implementation plan).

## Migration

No data migration. The bundle schema version (currently 1, in
`schema_spec.SCHEMA_VERSION`) does not change — the bundle is a strict
superset of the prior shape (more pages, no removed fields, same `.meta`
file format). Consumer skills reading prior bundles continue to work.

Existing workspaces that previously built clean under the old default
(`--keep-placeholders` absent) and have prose refs to placeholder pages will
*still* build clean under the new default — the new default keeps
placeholders, so the refs resolve. Only callers that explicitly opt into
`--drop-placeholders` will see the new error.

## Risks

- **False-positive risk:** the resolver is fairly forgiving (exact match +
  basename shorthand). The only way to get a false positive is for a page
  to wikilink a slug that genuinely doesn't exist anywhere in the wiki,
  which is itself a curator-side authoring bug that lint already catches in
  strict mode. Net: minimal.
- **Performance risk:** the check walks every page body and frontmatter
  once. On a 200-page wiki with ~10 wikilinks per page, that's ~2000
  resolutions, each O(1) in `kept_slugs`. Negligible.
- **Curator friction:** callers passing `--drop-placeholders` will now see
  build failures where the build previously succeeded. This is the
  intended behaviour; the failure points the curator at the exact prose
  refs to fix.

## Out-of-scope follow-ups

These were raised in the Q3 comparison but explicitly scoped out:

- **Empty "Top topics" in `wiki-manifest`** (finding #4 from the
  comparison). The manifest template has an HTML-comment placeholder that
  the build never replaces.
- **Bundle `feedback.md` as a one-way channel** (finding #3). Curator-side
  known-gap entries from `.forge/feedback.md` do not travel to the bundle.
  Could be addressed by a separate `gaps.md` build artifact.

Each deserves its own spec.
