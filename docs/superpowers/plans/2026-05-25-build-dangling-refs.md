# Build-time dangling-ref handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `confidence: placeholder` pages by default and fail the build if any prose `[[wikilink]]` or frontmatter typed-edge in the bundle points at a dropped or missing slug.

**Architecture:** Two layers. (1) Default-flip in `.forge/lib/build.py` argparse — `--keep-placeholders` becomes `--drop-placeholders` (opt-in). (2) New `validate_no_dangling_refs(kept_pages, kept_slugs)` helper in `build.py`, called between the drop pass and any writes; uses existing `wikilinks.extract_prose_links` and `wikilinks.extract_frontmatter_edges`. `index.write_links_tsv` is tightened to assert on unresolved targets (defense-in-depth, no longer reachable after step 1).

**Tech Stack:** Python 3 (stdlib only), pytest. Helper modules live under `.forge/lib/`; tests under `tests/` with `conftest.py` adding `.forge/lib/` to `sys.path`.

**Spec:** `docs/superpowers/specs/2026-05-25-build-dangling-refs-design.md`

---

## File structure

- **Modify:** `.forge/lib/build.py` — add `validate_no_dangling_refs`, call site, flip argparse default.
- **Modify:** `.forge/lib/index.py` — tighten `write_links_tsv` to assert on unresolved targets.
- **Modify:** `.forge/templates/SKILL.md.tmpl` — add "Known gaps" paragraph.
- **Create:** `tests/test_build_dangling.py` — unit tests for the helper.
- **Create:** `tests/INTEGRATION_build.md` — manual runbook for end-to-end verification.

No new modules. `.forge/lib/wikilinks.py` already exports `extract_prose_links`, `extract_frontmatter_edges`, `normalize_target`, and `resolve` — the helper composes them.

---

## Task 1: `validate_no_dangling_refs` — prose-link checking

**Files:**
- Create: `tests/test_build_dangling.py`
- Modify: `.forge/lib/build.py` (add new function near `should_drop`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_dangling.py` with three tests covering the simplest prose-link cases:

```python
"""Unit tests for build.validate_no_dangling_refs."""
import pytest

import build


def _page(slug, page_type, body, **fm):
    """Helper: synthesize a (slug, page_type, fm, body) tuple."""
    fm.setdefault("title", slug.rsplit("/", 1)[-1])
    return (slug, page_type, fm, body)


def test_clean_pages_set_does_not_raise():
    pages = [
        _page("concepts/a", "concept", "See [[concepts/b]] for context."),
        _page("concepts/b", "concept", "A standalone page."),
    ]
    kept_slugs = {"concepts/a", "concepts/b"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise


def test_dangling_prose_link_raises_systemexit(capsys):
    pages = [
        _page("concepts/a", "concept", "See [[concepts/missing]] for context."),
    ]
    kept_slugs = {"concepts/a"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    assert "concepts/a" in err
    assert "body" in err
    assert "[[concepts/missing]]" in err
    assert "1 dangling reference" in str(excinfo.value)


def test_wikilink_inside_html_comment_is_ignored():
    pages = [
        _page("concepts/a", "concept", "Body. <!-- TODO [[concepts/missing]] --> end."),
    ]
    kept_slugs = {"concepts/a"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_dangling.py -v`
Expected: 3 FAIL with `AttributeError: module 'build' has no attribute 'validate_no_dangling_refs'`.

- [ ] **Step 3: Implement the minimal helper in `.forge/lib/build.py`**

Add this function immediately after `should_drop` (around line 50) and add the import at the top of the file. The import section currently ends with `import index` — add `import wikilinks as WL` below it.

```python
def validate_no_dangling_refs(kept_pages, kept_slugs):
    """Fail the build if any prose [[wikilink]] or frontmatter typed-edge in
    `kept_pages` points at a slug not in `kept_slugs`.

    Emits one diagnostic line per dangling ref on stderr, sorted by
    (from_slug, source, target), then raises SystemExit with the total
    count. The order is deterministic so curators can diff successive runs.
    """
    basename_index = {}
    for slug in kept_slugs:
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)

    def resolves(target):
        return WL.resolve(WL.normalize_target(target), kept_slugs, basename_index) is not None

    dangling = []  # list of (from_slug, source, target)
    for slug, pt, fm, body in kept_pages:
        if pt is None:
            continue  # meta files like manifest.md have no slug-typed refs to validate
        if isinstance(body, str):
            for target in WL.extract_prose_links(body):
                if not resolves(target):
                    dangling.append((slug, "body", target))

    if not dangling:
        return
    dangling.sort()
    for from_slug, source, target in dangling:
        print(f"dangling-ref: {from_slug}  {source}  -->  [[{target}]]",
              file=sys.stderr)
    raise SystemExit(f"build aborted: {len(dangling)} dangling reference(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_dangling.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_build_dangling.py .forge/lib/build.py
git commit -m "feat(build): validate_no_dangling_refs — prose link checking"
```

---

## Task 2: Extend helper to typed-edge frontmatter + basename shorthand

**Files:**
- Modify: `tests/test_build_dangling.py` (add 2 tests)
- Modify: `.forge/lib/build.py` (extend `validate_no_dangling_refs`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_dangling.py`:

```python
def test_dangling_typed_edge_raises_systemexit(capsys):
    pages = [
        _page(
            "claims/a",
            "claim",
            "A claim body.",
            supersedes=["claims/missing"],
        ),
    ]
    kept_slugs = {"claims/a"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    assert "claims/a" in err
    assert "frontmatter:supersedes" in err
    assert "[[claims/missing]]" in err
    assert "1 dangling reference" in str(excinfo.value)


def test_basename_shorthand_resolves():
    """A prose link `[[sgd]]` resolves to `concepts/sgd` if that's the only match."""
    pages = [
        _page("concepts/a", "concept", "See [[sgd]] for context."),
        _page("concepts/sgd", "concept", "SGD page body."),
    ]
    kept_slugs = {"concepts/a", "concepts/sgd"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_build_dangling.py -v`
Expected: 3 PASS (from Task 1) and 2 FAIL. The typed-edge test fails because typed edges are not yet checked; the basename test fails because the resolver path is in place (no new code needed for it — but verifying it works is the point of the test).

If the basename test already passes, that's fine — it confirms the existing `WL.resolve` does the right thing. The typed-edge test must fail.

- [ ] **Step 3: Extend the helper to check typed edges**

In `.forge/lib/build.py`, modify `validate_no_dangling_refs` — add the typed-edge loop inside the page iteration. The complete function becomes:

```python
def validate_no_dangling_refs(kept_pages, kept_slugs):
    """Fail the build if any prose [[wikilink]] or frontmatter typed-edge in
    `kept_pages` points at a slug not in `kept_slugs`.

    Emits one diagnostic line per dangling ref on stderr, sorted by
    (from_slug, source, target), then raises SystemExit with the total
    count. The order is deterministic so curators can diff successive runs.
    """
    basename_index = {}
    for slug in kept_slugs:
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)

    def resolves(target):
        return WL.resolve(WL.normalize_target(target), kept_slugs, basename_index) is not None

    dangling = []  # list of (from_slug, source, target)
    for slug, pt, fm, body in kept_pages:
        if pt is None:
            continue
        if isinstance(fm, dict):
            for edge, target in WL.extract_frontmatter_edges(fm):
                if not resolves(target):
                    dangling.append((slug, f"frontmatter:{edge}", target))
        if isinstance(body, str):
            for target in WL.extract_prose_links(body):
                if not resolves(target):
                    dangling.append((slug, "body", target))

    if not dangling:
        return
    dangling.sort()
    for from_slug, source, target in dangling:
        print(f"dangling-ref: {from_slug}  {source}  -->  [[{target}]]",
              file=sys.stderr)
    raise SystemExit(f"build aborted: {len(dangling)} dangling reference(s)")
```

- [ ] **Step 4: Run tests to verify all 5 pass**

Run: `pytest tests/test_build_dangling.py -v`
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_build_dangling.py .forge/lib/build.py
git commit -m "feat(build): validate_no_dangling_refs — typed-edge checking"
```

---

## Task 3: Helper reports ALL dangling refs, sorted

**Files:**
- Modify: `tests/test_build_dangling.py` (add 1 test)

The current implementation already collects all refs before raising and sorts them. This task adds the test that locks in that behavior.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_dangling.py`:

```python
def test_reports_all_failures_in_sorted_order(capsys):
    pages = [
        _page(
            "z-page",
            "concept",
            "[[missing-c]] and [[missing-a]] and [[missing-b]].",
        ),
        _page("a-page", "concept", "[[missing-z]]."),
    ]
    kept_slugs = {"z-page", "a-page"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    lines = [l for l in err.splitlines() if l.startswith("dangling-ref:")]
    assert len(lines) == 4
    # Sorted by (from_slug, source, target):
    assert "a-page" in lines[0] and "[[missing-z]]" in lines[0]
    assert "z-page" in lines[1] and "[[missing-a]]" in lines[1]
    assert "z-page" in lines[2] and "[[missing-b]]" in lines[2]
    assert "z-page" in lines[3] and "[[missing-c]]" in lines[3]
    assert "4 dangling reference" in str(excinfo.value)
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `pytest tests/test_build_dangling.py::test_reports_all_failures_in_sorted_order -v`
Expected: PASS (the helper already implements this, this test locks it in).

If it fails: the helper has drifted — re-check `dangling.sort()` and the loop that emits each line. Do not move on until this test passes.

- [ ] **Step 3: Commit**

```bash
git add tests/test_build_dangling.py
git commit -m "test(build): lock in sorted, exhaustive dangling-ref reporting"
```

---

## Task 4: Wire `validate_no_dangling_refs` into `build()`

**Files:**
- Modify: `.forge/lib/build.py` (in `build()` function, between page-drop and any write)

- [ ] **Step 1: Read the current call site**

Open `.forge/lib/build.py` and locate the page-drop block, currently around lines 121-125:

```python
all_pages = list(index.load_pages(wiki_dir))
kept = [p for p in all_pages if not should_drop(p[0], p[1], p[2], drop_placeholder)]
kept_slugs = {slug for slug, pt, _, _ in kept if pt is not None}
n_dropped = len(all_pages) - len(kept)
print(f"    kept {len(kept)} pages ({n_dropped} dropped via draft/placeholder filter)")
```

- [ ] **Step 2: Insert the validation call after `kept_slugs` is computed and before the write loop**

Edit `.forge/lib/build.py`. After the `print(f"    kept {len(kept)} ...")` line and before the `for slug, pt, fm, body in kept:` loop (currently line 127), insert:

```python
    print("==> validating refs")
    validate_no_dangling_refs(kept, kept_slugs)
```

The complete contiguous block becomes:

```python
    all_pages = list(index.load_pages(wiki_dir))
    kept = [p for p in all_pages if not should_drop(p[0], p[1], p[2], drop_placeholder)]
    kept_slugs = {slug for slug, pt, _, _ in kept if pt is not None}
    n_dropped = len(all_pages) - len(kept)
    print(f"    kept {len(kept)} pages ({n_dropped} dropped via draft/placeholder filter)")

    print("==> validating refs")
    validate_no_dangling_refs(kept, kept_slugs)

    for slug, pt, fm, body in kept:
```

The validation runs before `bundle.mkdir(parents=True)` (line 114 in current code — actually the mkdir is *before* the kept computation, so a failed validation will leave an empty `dist/<name>-v<version>/` directory). Move the `bundle.mkdir` block to *after* the validation call to keep the invariant "no partial bundles on failure":

```python
    bundle = workspace / "dist" / f"{name}-v{version}"

    all_pages = list(index.load_pages(wiki_dir))
    kept = [p for p in all_pages if not should_drop(p[0], p[1], p[2], drop_placeholder)]
    kept_slugs = {slug for slug, pt, _, _ in kept if pt is not None}
    n_dropped = len(all_pages) - len(kept)
    print(f"    kept {len(kept)} pages ({n_dropped} dropped via draft/placeholder filter)")

    print("==> validating refs")
    validate_no_dangling_refs(kept, kept_slugs)

    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    out_wiki = bundle / "wiki"
    out_wiki.mkdir()
    out_meta = out_wiki / ".meta"
    out_meta.mkdir()

    for slug, pt, fm, body in kept:
```

(That is: keep the `bundle = workspace / "dist" / ...` path computation early, but defer the actual `mkdir` until after validation.)

- [ ] **Step 3: Manually verify on the bootstrapped workspace**

The current master workspace is bootstrapped and has a small wiki. Run:

```bash
cd /home/ubuntu/workspace/WikiForge
python3 .forge/lib/build.py --workspace . --version 0.0.0-test
```

Expected: build succeeds (no dangling refs in master's wiki); stderr is clean of `dangling-ref:` lines; a `dist/<name>-v0.0.0-test/` directory is created. Inspect:

```bash
ls dist/
rm -rf dist/wikiforge-v0.0.0-test  # cleanup; name may vary by manifest.md
```

- [ ] **Step 4: Run unit tests to confirm no regression**

Run: `pytest tests/test_build_dangling.py tests/test_index.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/build.py
git commit -m "feat(build): wire validate_no_dangling_refs into build()"
```

---

## Task 5: Flip argparse default — `--drop-placeholders` opt-in

**Files:**
- Modify: `.forge/lib/build.py` (argparse + main)

- [ ] **Step 1: Locate the argparse block**

In `.forge/lib/build.py`, find the `main()` function (around line 199). It currently contains:

```python
p.add_argument("--keep-placeholders", action="store_true",
               help="include pages with confidence: placeholder (default: drop)")
p.add_argument("--tar", action="store_true", help="also create a .tar.gz of the bundle")
args = p.parse_args()
build(args.workspace, args.version, not args.keep_placeholders, args.tar)
```

- [ ] **Step 2: Replace `--keep-placeholders` with `--drop-placeholders` (default: keep)**

Replace those four lines with:

```python
p.add_argument("--drop-placeholders", action="store_true",
               help="drop pages with confidence: placeholder "
                    "(default: keep — placeholders are known-gap markers)")
p.add_argument("--tar", action="store_true", help="also create a .tar.gz of the bundle")
args = p.parse_args()
build(args.workspace, args.version, args.drop_placeholders, args.tar)
```

The `build()` function signature and `should_drop()` are unchanged — only the bool now flows in as `False` by default.

- [ ] **Step 3: Manually verify default behavior keeps placeholders**

Create a minimal probe: in any wikiforge workspace with at least one placeholder page, run:

```bash
cd /home/ubuntu/workspace/WikiForge
python3 .forge/lib/build.py --workspace . --version 0.0.0-test --help | grep -i placeholder
```

Expected output:
```
  --drop-placeholders   drop pages with confidence: placeholder (default: keep —
                        placeholders are known-gap markers)
```

The `--keep-placeholders` flag must not appear.

- [ ] **Step 4: Run unit tests to confirm no regression**

Run: `pytest tests/ -v -k "build or index or lint"`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/build.py
git commit -m "feat(build): flip default — placeholders ship by default"
```

---

## Task 6: Tighten `index.write_links_tsv` to assert on unresolved targets

**Files:**
- Modify: `.forge/lib/index.py` (`write_links_tsv` function)
- Modify: `tests/test_index.py` (add 1 test)

After Task 4, no unresolved target can reach `write_links_tsv` — `validate_no_dangling_refs` will have aborted the build first. The silent-filter branches in `write_links_tsv` are dead code; replace them with assertions that catch any future regression of the upstream invariant.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_index.py`:

```python
def test_write_links_tsv_raises_on_unresolved_prose_target(tmp_path):
    """Defense-in-depth: validate_no_dangling_refs should catch this upstream,
    but if a caller bypasses it, write_links_tsv must fail loudly."""
    import pytest
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "a.md").write_text(
        _page("title: A\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    pages = list(index.load_pages(wiki))
    # Body has no dangling refs yet — inject one manually to simulate
    # a caller bypassing validate_no_dangling_refs:
    pages = [(slug, pt, fm, "See [[concepts/does-not-exist]].")
             for slug, pt, fm, body in pages if pt == "concept"]
    meta = wiki / ".meta"
    meta.mkdir()
    with pytest.raises(RuntimeError, match="unresolved target"):
        index.write_links_tsv(meta, pages, {"concepts/a"})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_index.py::test_write_links_tsv_raises_on_unresolved_prose_target -v`
Expected: FAIL — current behavior silently filters the unresolved target.

- [ ] **Step 3: Tighten `write_links_tsv` in `.forge/lib/index.py`**

Locate `write_links_tsv` (around line 66). The relevant branches currently read:

```python
            for edge, target in WL.extract_frontmatter_edges(fm):
                if edge not in S.EDGE_TYPES:
                    raise SystemExit(...)
                resolved = resolve(target)
                if resolved:
                    typed[(slug, resolved)] = edge
        if isinstance(body, str):
            for raw in WL.extract_prose_links(body):
                resolved = resolve(raw)
                if resolved:
                    prose.add((slug, resolved))
```

Replace the two `if resolved:` filters with assertions:

```python
            for edge, target in WL.extract_frontmatter_edges(fm):
                if edge not in S.EDGE_TYPES:
                    raise SystemExit(
                        f"unknown-edge-type: {slug} declares {edge!r}; "
                        f"vocabulary is {sorted(S.EDGE_TYPES)}"
                    )
                resolved = resolve(target)
                if not resolved:
                    raise RuntimeError(
                        f"internal: unresolved target {target!r} from {slug!r} "
                        f"(frontmatter:{edge}) reached write_links_tsv; "
                        f"validate_no_dangling_refs should have caught this"
                    )
                typed[(slug, resolved)] = edge
        if isinstance(body, str):
            for raw in WL.extract_prose_links(body):
                resolved = resolve(raw)
                if not resolved:
                    raise RuntimeError(
                        f"internal: unresolved target {raw!r} from {slug!r} "
                        f"(body) reached write_links_tsv; "
                        f"validate_no_dangling_refs should have caught this"
                    )
                prose.add((slug, resolved))
```

- [ ] **Step 4: Run all tests to confirm**

Run: `pytest tests/test_index.py tests/test_build_dangling.py -v`
Expected: all PASS, including the new defense-in-depth test.

- [ ] **Step 5: Commit**

```bash
git add tests/test_index.py .forge/lib/index.py
git commit -m "fix(index): write_links_tsv asserts on unresolved targets (no silent filter)"
```

---

## Task 7: SKILL.md template — add "Known gaps" paragraph

**Files:**
- Modify: `.forge/templates/SKILL.md.tmpl`

- [ ] **Step 1: Locate the insertion point**

Open `.forge/templates/SKILL.md.tmpl`. The "How to use" section ends at the line "less common" command listings (around line 30); "When to use this wiki vs. live retrieval" starts at line 32. The new section is inserted between them.

- [ ] **Step 2: Insert the new section**

Find:

```
- `bin/wiki-backlinks [--type EDGE] <slug>` — show pages linking to `<slug>` as `<edge>: <from>` lines

## When to use this wiki vs. live retrieval
```

Replace with:

```
- `bin/wiki-backlinks [--type EDGE] <slug>` — show pages linking to `<slug>` as `<edge>: <from>` lines

## Known gaps

Some pages ship with `confidence: placeholder`. These are **known gaps**: the curator has noted the topic is referenced by other pages but the canonical source has not yet been ingested. Read the stub for the citation hint — it names the paper, repo, or URL that would close the gap — then fall back to live retrieval. Do not treat placeholder content as authoritative.

## When to use this wiki vs. live retrieval
```

- [ ] **Step 3: Verify the template still renders**

The template uses `@VAR@` substitutions; the new paragraph is plain text with no variables, so substitution is unaffected. Sanity-check by running a build:

```bash
cd /home/ubuntu/workspace/WikiForge
python3 .forge/lib/build.py --workspace . --version 0.0.0-test
grep -A2 "## Known gaps" dist/*/SKILL.md
rm -rf dist/*-v0.0.0-test
```

Expected: the new section appears between "wiki-backlinks" and "When to use this wiki vs. live retrieval". No `@VAR@` placeholders remain anywhere in the output.

- [ ] **Step 4: Commit**

```bash
git add .forge/templates/SKILL.md.tmpl
git commit -m "docs(skill): add Known gaps section explaining placeholder pages"
```

---

## Task 8: Integration runbook

**Files:**
- Create: `tests/INTEGRATION_build.md`

This is a manual runbook in the style of `tests/INTEGRATION_ingest.md` / `tests/INTEGRATION_lint.md`. It documents the end-to-end scenarios for a future agent (or human) to reproduce.

- [ ] **Step 1: Create the runbook**

Write `tests/INTEGRATION_build.md`:

```markdown
# INTEGRATION — build: dangling-ref handling

Scope: verify that `build.py` (a) ships `confidence: placeholder` pages by
default, and (b) fails the build with a precise diagnostic if any prose or
typed-edge ref points at a dropped or missing slug. See
`docs/superpowers/specs/2026-05-25-build-dangling-refs-design.md` for the
design.

## Setup

Choose a scratch workspace. Example:

```sh
mkdir -p /tmp/wf-build-int && cd /tmp/wf-build-int
git init -q
# Copy a fresh bootstrapped wikiforge workspace here, or use one of the
# existing test worktrees under worktrees/wf-test-*.
```

For the rest of this runbook, `$WS` is the wikiforge workspace root.

## Scenario A — default build keeps placeholders

Pre-state:
- At least one page in `$WS/wiki/` has `confidence: placeholder`.
- At least one *other* page has a prose `[[<placeholder-slug>]]` reference.

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.0
```

Expected:
- Exit code 0.
- `dist/<name>-v0.1.0/` exists.
- The placeholder page is present in `dist/<name>-v0.1.0/wiki/<type>/<slug>.md`.
- `dist/<name>-v0.1.0/SKILL.md` contains the "## Known gaps" section.
- `dist/<name>-v0.1.0/wiki/.meta/pages.tsv` lists the placeholder page.

## Scenario B — `--drop-placeholders` fails on dangling refs

Pre-state: same as Scenario A.

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.1 --drop-placeholders 2> /tmp/wf-build-int.err
echo "exit=$?"
cat /tmp/wf-build-int.err
```

Expected:
- Exit code non-zero.
- stderr contains one `dangling-ref:` line per stale prose link plus one per
  stale typed edge, sorted by (from_slug, source, target).
- stderr ends with `build aborted: N dangling reference(s)` where N is the
  total count.
- `dist/<name>-v0.1.1/` does **not** exist (no partial bundle).

## Scenario C — `--drop-placeholders` succeeds after refs are removed

Pre-state: edit the page that referenced the placeholder. Remove the
`[[<placeholder-slug>]]` references (or replace with plain text).

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.2 --drop-placeholders
```

Expected:
- Exit code 0.
- `dist/<name>-v0.1.2/` exists.
- The placeholder page is **absent** from `dist/<name>-v0.1.2/wiki/`.
- `dist/<name>-v0.1.2/wiki/.meta/pages.tsv` does not list the placeholder page.

## Cleanup

```sh
rm -rf $WS/dist/*-v0.1.0 $WS/dist/*-v0.1.1 $WS/dist/*-v0.1.2
```
```

- [ ] **Step 2: Commit**

```bash
git add tests/INTEGRATION_build.md
git commit -m "test(build): integration runbook for dangling-ref handling"
```

---

## Task 9: Regression verification on multimodal-llm fixture

**Files:**
- No code changes. This task is a manual reproduction of the bug + fix on the real fixture that surfaced it.

- [ ] **Step 1: Locate the existing test worktree**

The `wf-test-multimodal-llm-20260525T025040Z` worktree at
`/home/ubuntu/workspace/WikiForge/worktrees/wf-test-multimodal-llm-20260525T025040Z`
has the full pipeline already run and a bundle built. It is **on a branch
created from a master commit that predates this fix** — to verify the fix
against it, you must merge or rebase the fix into the worktree's branch
first. Simplest: re-run the fix against a fresh worktree created from the
current master HEAD.

- [ ] **Step 2: Create a fresh test worktree from current master**

```bash
cd /home/ubuntu/workspace/WikiForge
TS=$(date -u +%Y%m%dT%H%M%SZ)
git worktree add worktrees/wf-build-regression-$TS -b test/build-regression-$TS master
echo "Worktree: worktrees/wf-build-regression-$TS"
```

Bootstrap a minimal workspace there or copy the multimodal-llm bundle's source wiki. (If reusing the existing `wf-test-multimodal-llm-20260525T025040Z` worktree, cherry-pick the fix commits onto its branch first; this avoids re-running ingest.)

For the simplest verification, **reuse the existing worktree** with a cherry-pick:

```bash
cd worktrees/wf-test-multimodal-llm-20260525T025040Z
git fetch --all  # no-op if no remote, fine
# Cherry-pick the fix commits from master (use the hashes from your work):
git cherry-pick <commit-from-task-1> <commit-from-task-2> ... <commit-from-task-7>
```

- [ ] **Step 3: Default build — expect 20-page bundle, no errors**

```bash
cd /home/ubuntu/workspace/WikiForge/worktrees/wf-test-multimodal-llm-20260525T025040Z
python3 .forge/lib/build.py --workspace . --version 0.0.2
```

Expected:
- Exit code 0.
- Output: `kept 20 pages (0 dropped via draft/placeholder filter)`.
- `dist/multimodal-llm-v0.0.2/wiki/concepts/clip.md` and `clip-loss.md` exist.

```bash
ls dist/multimodal-llm-v0.0.2/wiki/concepts/
```

Expected: includes `clip.md` and `clip-loss.md`.

- [ ] **Step 4: `--drop-placeholders` build — expect 5 dangling-ref errors**

```bash
python3 .forge/lib/build.py --workspace . --version 0.0.3 --drop-placeholders 2> /tmp/wf-drop.err
echo "exit=$?"
cat /tmp/wf-drop.err
```

Expected stderr (exact text, in sorted order):
```
dangling-ref: concepts/encoder-free-multimodal             body  -->  [[concepts/clip-loss]]
dangling-ref: entities/llava                               body  -->  [[concepts/clip]]
dangling-ref: sources/llava-visual-instruction-tuning      body  -->  [[concepts/clip]]
dangling-ref: sources/llava-visual-instruction-tuning      body  -->  [[concepts/clip-loss]]
dangling-ref: sources/tuna-2-paper                         body  -->  [[concepts/clip]]
build aborted: 5 dangling reference(s)
```

Exit code: non-zero. `dist/multimodal-llm-v0.0.3/` must not exist.

- [ ] **Step 5: Document the result**

Append a brief note to `tests/INTEGRATION_build.md` (created in Task 8) under a new section "## Real-world regression":

```markdown

## Real-world regression — multimodal-llm fixture (2026-05-25)

The bug was first surfaced on the multimodal-llm fixture (5 dangling refs to
`concepts/clip` and `concepts/clip-loss` after the build dropped them as
placeholders). After this fix:

- Default build: 20 pages (was 18). Both `concepts/clip` and
  `concepts/clip-loss` ship as `confidence: placeholder` known-gap markers.
- `--drop-placeholders`: fails fast with 5 dangling-ref diagnostics, no
  partial bundle written.

Reproducible from any bootstrapped workspace that ingested the four sources
in `dev-tools/fixtures/multimodal-llm/raw/`.
```

- [ ] **Step 6: Commit and clean up**

```bash
git add tests/INTEGRATION_build.md
git commit -m "test(build): document multimodal-llm regression case"
rm -rf dist/multimodal-llm-v0.0.2 dist/multimodal-llm-v0.0.3
```

---

## Self-review against the spec

Spec coverage (each spec section, mapped to its task):

- **Behaviour change → argparse** → Task 5.
- **Behaviour change → `should_drop`** → no change required (logic unchanged); covered implicitly by Task 5.
- **Safety layer → new helper** → Tasks 1, 2, 3.
- **Safety layer → call site** → Task 4.
- **Safety layer → diagnostic format** → Tasks 1, 3 (exact format locked in by tests).
- **Safety layer → `write_links_tsv` cleanup** → Task 6.
- **SKILL.md template update** → Task 7.
- **Tests → unit tests** → Tasks 1, 2, 3 (covers all 6 unit tests from the spec).
- **Tests → integration test** → Task 8.
- **Tests → regression coverage on multimodal-llm fixture** → Task 9.
- **Migration** → no migration needed; verified by Tasks 4 and 9 (default-args build on master and on the fixture both succeed).
- **Risks → performance, false positives, curator friction** → addressed by design; no implementation step needed.

No spec section is uncovered.

Placeholder scan: no "TBD" / "TODO" / "fill in" / "similar to Task N" / abstract phrasing — all code is concrete. The one place a task defers a decision ("if reusing the existing worktree…" in Task 9 Step 2) gives both alternatives explicitly.

Type/name consistency: `validate_no_dangling_refs(kept_pages, kept_slugs)` is consistent across Tasks 1, 2, 3, 4. The diagnostic format `"dangling-ref: <from-slug>  <source>  -->  [[<target>]]"` is consistent across Tasks 1, 2, 3, 9. `--drop-placeholders` flag name is consistent across Tasks 5, 8, 9.

---

## Out-of-scope follow-up (flagged for separate work)

The `dev-tools/fixtures/multimodal-llm/expectations.md` file (on the
`dev/test-harness` branch, not on master) currently asserts "wiki/sources/
has at least 4 pages" and the bundle ships 18. After this fix is merged and
the harness re-runs against a bundle built with the new default, the
fixture's expectations.md should be updated to reflect 20 bundle pages.
This is a docs-only change on a separate branch — track as a follow-up.
