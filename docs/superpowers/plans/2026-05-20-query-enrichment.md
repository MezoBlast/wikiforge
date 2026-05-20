# Query Skill Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the curator-side `query` skill operable and complete — give the curator workspace a `wiki/.meta/` index, wire a curator gap-feedback loop into `explorer`, and rewrite the `query` SKILL.md.

**Architecture:** A new `.forge/lib/index.py` owns the index-writing logic currently inlined in `build.py`; `build.py` imports it. `wiki/.meta/` becomes a wiki artifact maintained by `ingest` (after a run) and `lint --fix` (on demand) — `query` only reads it. A new append-only `.forge/feedback.md` receives `query-gap` entries that `explorer` harvests. The `query` SKILL.md is rewritten around the principle "answer from the wiki, not from memory."

**Tech Stack:** Python 3 (stdlib + `pyyaml`), `pytest`, POSIX shell (`bin/wiki-*`, unchanged), markdown skill files.

**Reference spec:** `docs/superpowers/specs/2026-05-20-query-enrichment-design.md`

---

## File structure

**New files:**
- `.forge/lib/index.py` — index module: `load_pages`, `write_pages_tsv`, `write_links_tsv`, `write_meta`, `main()`. Sole owner of `.meta/` TSV generation.
- `tests/test_index.py` — unit tests for `index.py`.
- `tests/INTEGRATION_query.md` — manual integration runbook for the `query` skill.
- `.forge/feedback.md` — exists only in bootstrapped curator workspaces (seeded by `bootstrap.py`); not committed to the framework repo.

**Modified files:**
- `.forge/lib/build.py` — import `index`, drop the three inlined index functions.
- `.forge/lib/lint.py` — `--fix` regenerates `wiki/.meta/`; new `stale-index` rule.
- `.forge/lib/bootstrap.py` — seed `.forge/feedback.md`.
- `tests/test_lint.py`, `tests/test_bootstrap.py` — new tests.
- `.forge/skills/query/SKILL.md` — full rewrite.
- `.forge/skills/lint/SKILL.md`, `.forge/skills/ingest/SKILL.md`, `.forge/skills/explorer/SKILL.md` — targeted edits.
- `schema.md` — `## Build artifacts` → `## Index artifacts`.
- `templates/CLAUDE.md.tmpl`, `templates/AGENTS.md.tmpl`, `templates/.gitignore.tmpl`, `.gitignore`, `bootstrap.md`.

---

## Task 1: Create the shared indexer `.forge/lib/index.py`

**Files:**
- Create: `.forge/lib/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index.py`:

```python
import datetime

import index


def _page(text):
    return "---\n" + text + "\n---\n\nbody\n"


def _concept(title, extra=""):
    return _page(
        f"title: {title}\ntype: concept\n"
        f"created: 2026-01-01\nlast_verified: 2026-01-01\nconfidence: likely" + extra
    )


def test_load_pages_classifies_pages_and_meta(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(_concept("SGD"), encoding="utf-8")
    (wiki / "manifest.md").write_text("# manifest\n", encoding="utf-8")
    pages = {slug: pt for slug, pt, _, _ in index.load_pages(wiki)}
    assert pages["concepts/sgd"] == "concept"
    assert pages["manifest"] is None  # meta file -> page_type None


def test_write_meta_writes_both_tsvs(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(_concept("SGD"), encoding="utf-8")
    meta = wiki / ".meta"
    index.write_meta(meta, index.load_pages(wiki))
    pages_tsv = (meta / "pages.tsv").read_text(encoding="utf-8")
    assert pages_tsv.splitlines()[0] == "path\ttitle\ttype\ttags\tlast_verified\tconfidence"
    assert "concepts/sgd\tSGD\tconcept\t" in pages_tsv
    links_tsv = (meta / "links.tsv").read_text(encoding="utf-8")
    assert links_tsv.splitlines()[0] == "from\tto\tedge_type"


def test_write_links_typed_edge_wins_over_prose(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "claims").mkdir(parents=True)
    (wiki / "claims" / "b.md").write_text(
        _page("title: B\ntype: claim\ncreated: 2026-01-01\nlast_verified: 2026-01-01\n"
              "confidence: likely\nstatus: open\nevidence: [sources/x]\ncounter_evidence: []"),
        encoding="utf-8")
    (wiki / "claims" / "a.md").write_text(
        "---\ntitle: A\ntype: claim\ncreated: 2026-01-01\nlast_verified: 2026-01-01\n"
        "confidence: likely\nstatus: open\nevidence: [sources/x]\ncounter_evidence: []\n"
        "supersedes: [claims/b]\n---\n\nSee [[claims/b]] for the older view.\n",
        encoding="utf-8")
    meta = wiki / ".meta"
    index.write_meta(meta, index.load_pages(wiki))
    links = (meta / "links.tsv").read_text(encoding="utf-8")
    assert "claims/a\tclaims/b\tsupersedes" in links
    assert "claims/a\tclaims/b\treferences" not in links  # typed edge won


def test_main_indexes_draft_pages(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "draft-page.md").write_text(
        _concept("Draft", extra="\ndraft: true"), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["index", "--wiki", str(wiki)])
    index.main()
    pages_tsv = (wiki / ".meta" / "pages.tsv").read_text(encoding="utf-8")
    assert "concepts/draft-page" in pages_tsv  # curator index keeps drafts
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'index'`.

- [ ] **Step 3: Create `.forge/lib/index.py`**

```python
#!/usr/bin/env python3
"""index.py — build the wiki/.meta/ index (pages.tsv, links.tsv).

wiki/.meta/ is a derived index of the wiki, consumed by the bin/wiki-* read
scripts. It is a wiki artifact: maintained by whoever mutates the wiki (ingest
after a run, lint --fix on demand) and produced into the bundle by build.py.

Run as a CLI to regenerate the curator workspace index:

    python3 .forge/lib/index.py [--wiki wiki]

The CLI indexes every page, including drafts and placeholders — the curator
searches work in progress. build.py imports these functions and passes its own
filtered (build-eligible) page set.
"""
import argparse
import datetime
import sys
from pathlib import Path

# allow `import schema_spec`, etc. when invoked as `python3 .forge/lib/index.py`
sys.path.insert(0, str(Path(__file__).parent))

import schema_spec as S
import frontmatter as FM
import wikilinks as WL


def load_pages(wiki_dir):
    """Yield (slug, page_type, fm, body) for every page under wiki/.

    For meta files (manifest, index, log, out_of_scope), page_type is None and
    fm is None. Pages with unparseable frontmatter are skipped (lint flags them).
    """
    for md in sorted(wiki_dir.rglob("*.md")):
        if ".meta" in md.parts:
            continue
        rel = md.relative_to(wiki_dir).with_suffix("")
        slug = rel.as_posix()
        if slug in S.META_FILES:
            yield slug, None, None, md.read_text(encoding="utf-8")
            continue
        try:
            fm, body = FM.load(md)
        except FM.FrontmatterError:
            continue  # lint already flagged it
        page_type = S.DIR_TYPES.get(slug.split("/", 1)[0])
        yield slug, page_type, fm, body


def write_pages_tsv(meta_dir, pages):
    """Write meta_dir/pages.tsv. meta_dir must already exist."""
    rows = ["path\ttitle\ttype\ttags\tlast_verified\tconfidence"]
    for slug, pt, fm, _ in pages:
        if pt is None:
            continue
        title = str(fm.get("title", slug)).replace("\t", " ").replace("\n", " ")
        tags = ",".join(str(t) for t in (fm.get("tags") or []))
        lv = fm.get("last_verified")
        if isinstance(lv, datetime.date):
            lv = lv.isoformat()
        conf = fm.get("confidence", "")
        rows.append(f"{slug}\t{title}\t{pt}\t{tags}\t{lv}\t{conf}")
    (meta_dir / "pages.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_links_tsv(meta_dir, pages, kept_slugs):
    """Write meta_dir/links.tsv. Frontmatter typed edges win over prose for the
    same (from, to) pair. meta_dir must already exist."""
    basename_index = {}
    for slug in kept_slugs:
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)

    def resolve(target):
        return WL.resolve(WL.normalize_target(target), kept_slugs, basename_index)

    typed = {}        # (from, to) -> edge_type
    prose = set()     # (from, to) for references

    for slug, _, fm, body in pages:
        if isinstance(fm, dict):
            for edge, target in WL.extract_frontmatter_edges(fm):
                if edge not in S.EDGE_TYPES:
                    raise SystemExit(
                        f"unknown-edge-type: {slug} declares {edge!r}; "
                        f"vocabulary is {sorted(S.EDGE_TYPES)}"
                    )
                resolved = resolve(target)
                if resolved:
                    typed[(slug, resolved)] = edge
        if isinstance(body, str):
            for raw in WL.extract_prose_links(body):
                resolved = resolve(raw)
                if resolved:
                    prose.add((slug, resolved))

    rows = ["from\tto\tedge_type"]
    seen = set()
    for (f, t), edge in sorted(typed.items()):
        rows.append(f"{f}\t{t}\t{edge}")
        seen.add((f, t))
    for (f, t) in sorted(prose):
        if (f, t) in seen:
            continue
        rows.append(f"{f}\t{t}\treferences")
    (meta_dir / "links.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_meta(meta_dir, pages):
    """Create meta_dir and write both pages.tsv and links.tsv from `pages`
    (an iterable of (slug, page_type, fm, body) tuples, as load_pages yields)."""
    pages = list(pages)
    kept_slugs = {slug for slug, pt, _, _ in pages if pt is not None}
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_pages_tsv(meta_dir, pages)
    write_links_tsv(meta_dir, pages, kept_slugs)


def main():
    p = argparse.ArgumentParser(prog="index",
                                description="regenerate the wiki/.meta/ index")
    p.add_argument("--wiki", default="wiki", help="path to wiki dir (default: wiki)")
    args = p.parse_args()
    wiki_dir = Path(args.wiki).resolve()
    if not wiki_dir.is_dir():
        print(f"index: wiki dir not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)
    pages = list(load_pages(wiki_dir))
    meta_dir = wiki_dir / ".meta"
    write_meta(meta_dir, pages)
    n = sum(1 for _, pt, _, _ in pages if pt is not None)
    print(f"indexed {n} page(s) -> {meta_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_index.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/index.py tests/test_index.py
git commit -m "feat: add index.py shared wiki indexer

Owns load_pages + pages.tsv/links.tsv generation, extracted so the
curator workspace can regenerate wiki/.meta/ without a full build.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Refactor `build.py` to use `index.py`

**Files:**
- Modify: `.forge/lib/build.py`

- [ ] **Step 1: Update the import block**

In `.forge/lib/build.py`, replace:

```python
import schema_spec as S
import frontmatter as FM
import wikilinks as WL
import provenance as PR
import lint as LINT
```

with (drop `wikilinks`, add `index`):

```python
import schema_spec as S
import frontmatter as FM
import provenance as PR
import lint as LINT
import index
```

- [ ] **Step 2: Delete the three inlined functions**

Delete these three function definitions from `build.py` entirely — they now live in `index.py`:
- `def load_pages(wiki_dir):` and its body
- `def write_pages_tsv(out_meta, kept):` and its body
- `def write_links_tsv(out_meta, kept, kept_slugs):` and its body

Leave `should_drop`, `copy_snippets`, `get_git_sha`, `render_template`,
`scope_summary_from_manifest`, `build`, and `main` in place.

- [ ] **Step 3: Update the three call sites inside `build()`**

Replace `all_pages = list(load_pages(wiki_dir))` with:

```python
    all_pages = list(index.load_pages(wiki_dir))
```

Replace `write_pages_tsv(out_meta, kept)` with:

```python
    index.write_pages_tsv(out_meta, kept)
```

Replace `write_links_tsv(out_meta, kept, kept_slugs)` with:

```python
    index.write_links_tsv(out_meta, kept, kept_slugs)
```

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -nE '\b(load_pages|write_pages_tsv|write_links_tsv|WL)\b' .forge/lib/build.py`
Expected: every match is prefixed with `index.` (e.g. `index.load_pages`). No bare
`load_pages`, no `WL`, no `def load_pages`.

- [ ] **Step 5: Verify build.py still imports and the suite passes**

Run: `python3 -c "import sys; sys.path.insert(0, '.forge/lib'); import build"`
Expected: no output, exit 0.

Run: `python3 -m pytest -q`
Expected: PASS — all tests green (test_index.py covers the moved logic).

- [ ] **Step 6: Commit**

```bash
git add .forge/lib/build.py
git commit -m "refactor: build.py uses index.py for .meta/ generation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add the `stale-index` lint rule

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lint.py`:

```python
def test_stale_index_warns_when_meta_missing(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert any(i.code == "stale-index" for i in issues)


def test_stale_index_silent_when_meta_fresh(tmp_path):
    import os
    import time
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    meta = wiki / ".meta"
    meta.mkdir()
    pages_tsv = meta / "pages.tsv"
    pages_tsv.write_text("path\ttitle\ttype\ttags\tlast_verified\tconfidence\n",
                         encoding="utf-8")
    future = time.time() + 10
    os.utime(pages_tsv, (future, future))  # index newer than the page
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert not any(i.code == "stale-index" for i in issues)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_lint.py -k stale_index -v`
Expected: `test_stale_index_warns_when_meta_missing` FAILS (no `stale-index` issue
emitted); `test_stale_index_silent_when_meta_fresh` passes vacuously.

- [ ] **Step 3: Add the `check_stale_index` function**

In `.forge/lib/lint.py`, add this function immediately before `def lint(`:

```python
def check_stale_index(wiki_dir, issues):
    """Warn if wiki/.meta/pages.tsv is missing or older than the newest page."""
    meta = wiki_dir / ".meta" / "pages.tsv"
    newest = 0.0
    for md in wiki_dir.rglob("*.md"):
        if ".meta" in md.parts:
            continue
        newest = max(newest, md.stat().st_mtime)
    if not meta.exists():
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            "wiki/.meta/ index missing — run python3 .forge/lib/lint.py --fix"))
        return
    if meta.stat().st_mtime < newest:
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            "index older than newest wiki page — run python3 .forge/lib/lint.py --fix"))
```

- [ ] **Step 4: Call it from `lint()`**

In `def lint(`, immediately after the line `valid_slugs, basename_index, fm_map = build_indices(pages)`, add:

```python
    check_stale_index(wiki_dir, issues)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_lint.py -k stale_index -v`
Expected: PASS — 2 passed.

- [ ] **Step 6: Commit**

```bash
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: add stale-index lint rule

Warns when wiki/.meta/ is missing or older than the newest page, so
the normal lint cadence surfaces an index query depends on.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Make `lint --fix` regenerate `wiki/.meta/`

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint.py`:

```python
def test_fix_regenerates_meta_index(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    lint.fix(wiki, datetime.date(2026, 5, 20))
    meta = wiki / ".meta"
    assert (meta / "pages.tsv").exists()
    assert (meta / "links.tsv").exists()
    assert "concepts/sgd" in (meta / "pages.tsv").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_lint.py -k fix_regenerates_meta -v`
Expected: FAIL — `wiki/.meta/pages.tsv` does not exist after `fix`.

- [ ] **Step 3: Import `index` in lint.py**

In `.forge/lib/lint.py`, change the import block:

```python
import schema_spec as S
import frontmatter as FM
import wikilinks as WL
```

to:

```python
import schema_spec as S
import frontmatter as FM
import wikilinks as WL
import index
```

- [ ] **Step 4: Extend `fix()` to regenerate `.meta/`**

In `def fix(wiki_dir, today):`, the function currently ends with:

```python
    (wiki_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"rebuilt {wiki_dir / 'index.md'}")
```

Add two lines after it so the function ends:

```python
    (wiki_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"rebuilt {wiki_dir / 'index.md'}")
    meta_dir = wiki_dir / ".meta"
    index.write_meta(meta_dir, index.load_pages(wiki_dir))
    print(f"rebuilt {meta_dir}")
```

Also update the `fix` docstring from `"""Conservative auto-fix: rebuild index.md from current pages."""`
to `"""Conservative auto-fix: rebuild index.md and wiki/.meta/ from current pages."""`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_lint.py -k fix_regenerates_meta -v`
Expected: PASS — 1 passed.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — all tests green.

- [ ] **Step 7: Commit**

```bash
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: lint --fix regenerates wiki/.meta/ index

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Seed `.forge/feedback.md` during bootstrap

**Files:**
- Modify: `.forge/lib/bootstrap.py`
- Modify: `bootstrap.md`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap.py`:

```python
def test_seed_files_include_feedback(tmp_path):
    created = bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    assert ".forge/feedback.md" in created
    content = (tmp_path / ".forge/feedback.md").read_text()
    assert content.startswith("# .forge/feedback.md")


def test_seed_feedback_idempotent(tmp_path):
    bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    again = bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    assert ".forge/feedback.md" not in again  # already exists, not re-created
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_bootstrap.py -k feedback -v`
Expected: FAIL — `.forge/feedback.md` not in the created list.

- [ ] **Step 3: Add `.forge/feedback.md` to `SEED_FILES`**

In `.forge/lib/bootstrap.py`, in the `SEED_FILES` dict, add this entry after the
`".forge/log.md"` entry (before the closing `}`):

```python
    ".forge/feedback.md": (
        "# .forge/feedback.md — append-only curator feedback log\n"
        "<!-- query appends query-gap entries here; explorer harvests them. -->\n"
        "<!-- See .forge/skills/query/SKILL.md for the entry format. -->\n"
    ),
```

- [ ] **Step 4: Update the bootstrap.py docstring**

In `.forge/lib/bootstrap.py`, in the module docstring, change:

```
  2. Creates the seed empty append-only files (`wiki/index.md`, `wiki/log.md`,
     `.forge/queue.md`, `.forge/log.md`) with header lines.
```

to:

```
  2. Creates the seed append-only files (`wiki/index.md`, `wiki/log.md`,
     `.forge/queue.md`, `.forge/log.md`, `.forge/feedback.md`) with header lines.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_bootstrap.py -k feedback -v`
Expected: PASS — 2 passed.

- [ ] **Step 6: Update `bootstrap.md`**

In `bootstrap.md`, make three edits:

(a) Change the line:

```
- Creates seed append-only files (`wiki/index.md`, `wiki/log.md`, `.forge/queue.md`, `.forge/log.md`) with header lines.
```

to:

```
- Creates seed append-only files (`wiki/index.md`, `wiki/log.md`, `.forge/queue.md`, `.forge/log.md`, `.forge/feedback.md`) with header lines.
```

(b) Change the verification line:

```
test -f wiki/index.md && test -f wiki/log.md && test -f .forge/queue.md && test -f .forge/log.md || echo "MISSING SEED"
```

to:

```
test -f wiki/index.md && test -f wiki/log.md && test -f .forge/queue.md && test -f .forge/log.md && test -f .forge/feedback.md || echo "MISSING SEED"
```

(c) In the "What lands in this commit" list, change:

```
- `.forge/queue.md`, `.forge/log.md`, `.forge/notify.md`, `.forge/bootstrap.log`
```

to:

```
- `.forge/queue.md`, `.forge/log.md`, `.forge/feedback.md`, `.forge/notify.md`, `.forge/bootstrap.log`
```

- [ ] **Step 7: Commit**

```bash
git add .forge/lib/bootstrap.py bootstrap.md tests/test_bootstrap.py
git commit -m "feat: seed .forge/feedback.md during bootstrap

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Reframe `schema.md` Build artifacts → Index artifacts

**Files:**
- Modify: `schema.md`

- [ ] **Step 1: Rewrite the section heading and intro**

In `schema.md`, replace:

```
## Build artifacts

After build, two TSV files in `wiki/.meta/` index the wiki:
```

with:

```
## Index artifacts

Two TSV files in `wiki/.meta/` index the wiki. They are produced by
`.forge/lib/index.py` — invoked on demand in the curator workspace (by `ingest`
after a run and by `lint --fix`) and by `build.py` when assembling a bundle. The
curator-side index covers every page; the bundle-side index covers only the
pages that ship.
```

- [ ] **Step 2: Rewrite the closing line of the section**

In the same section, replace:

```
Both files are regenerated on every build. They are not hand-edited.
```

with:

```
Both files are regenerated by `index.py`; they are derived artifacts and are
never hand-edited. In the curator workspace `wiki/.meta/` is gitignored.
```

- [ ] **Step 3: Verify the schema version was not bumped**

Run: `grep -n 'schema_version' schema.md`
Expected: still `schema_version: 1` — this change does not alter the TSV column
formats, so no version bump.

- [ ] **Step 4: Commit**

```bash
git add schema.md
git commit -m "docs: reframe schema.md Build artifacts as Index artifacts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Template and gitignore updates

**Files:**
- Modify: `templates/CLAUDE.md.tmpl`
- Modify: `templates/AGENTS.md.tmpl`
- Modify: `templates/.gitignore.tmpl`
- Modify: `.gitignore`

- [ ] **Step 1: Update `templates/CLAUDE.md.tmpl` — append-only rule**

Replace:

```
6. **Append-only state.** `wiki/log.md`, `.forge/log.md`, `.forge/queue.md`, `.forge/requests/inbox/`, `.forge/requests/responses/` are append-only. Don't rewrite history.
```

with:

```
6. **Append-only state.** `wiki/log.md`, `.forge/log.md`, `.forge/queue.md`, `.forge/feedback.md`, `.forge/requests/inbox/`, `.forge/requests/responses/` are append-only. Don't rewrite history.
```

- [ ] **Step 2: Update `templates/CLAUDE.md.tmpl` — directory tree**

Replace:

```
  queue.md             # ingest queue
  log.md               # curator-side operation log
```

with:

```
  queue.md             # ingest queue
  feedback.md          # query-gap log; harvested by explorer
  log.md               # curator-side operation log
```

- [ ] **Step 3: Apply the same two edits to `templates/AGENTS.md.tmpl`**

`templates/AGENTS.md.tmpl` contains the identical append-only rule line and the
identical `queue.md` / `log.md` tree lines. Apply the exact same two
replacements from Steps 1 and 2 to it.

- [ ] **Step 4: Update `templates/.gitignore.tmpl`**

At the end of `templates/.gitignore.tmpl`, add:

```
# derived wiki index — regenerated by .forge/lib/index.py
wiki/.meta/
```

- [ ] **Step 5: Update the framework `.gitignore`**

Read `.gitignore` (the repo-root file). At its end, add the same two lines:

```
# derived wiki index — regenerated by .forge/lib/index.py
wiki/.meta/
```

- [ ] **Step 6: Verify**

Run: `grep -rn 'feedback.md' templates/CLAUDE.md.tmpl templates/AGENTS.md.tmpl`
Expected: each file shows `feedback.md` in both the append-only rule and the tree.

Run: `grep -n 'wiki/.meta' templates/.gitignore.tmpl .gitignore`
Expected: a match in each file.

- [ ] **Step 7: Commit**

```bash
git add templates/CLAUDE.md.tmpl templates/AGENTS.md.tmpl templates/.gitignore.tmpl .gitignore
git commit -m "chore: register .forge/feedback.md and gitignore wiki/.meta/

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Document the `stale-index` rule in the lint skill

**Files:**
- Modify: `.forge/skills/lint/SKILL.md`

- [ ] **Step 1: Add the rule to the rule table**

In `.forge/skills/lint/SKILL.md`, in the rule-code table, add this row after the
`claim-supports-without-evidence` row (keep the table's column alignment
roughly consistent):

```
| `stale-index`                     | warning  | `wiki/.meta/` index is missing or older than the newest page.              |
```

- [ ] **Step 2: Note the `--fix` behavior change**

In the same file, find the line describing `--fix`:

```
python3 .forge/lib/lint.py --fix          # rebuild index.md from current pages
```

Replace it with:

```
python3 .forge/lib/lint.py --fix          # rebuild index.md and wiki/.meta/ from current pages
```

Then find the `--fix` paragraph under "Decisions, not rules":

```
- `--fix` is conservative: it rebuilds `index.md` from the current page set. It does not delete pages, does not silently mutate frontmatter, and does not move files.
```

Replace it with:

```
- `--fix` is conservative: it rebuilds `index.md` and the `wiki/.meta/` index (`pages.tsv`, `links.tsv`) from the current page set. It does not delete pages, does not silently mutate frontmatter, and does not move files. `--fix` is the on-demand way to clear a `stale-index` warning.
```

- [ ] **Step 3: Verify**

Run: `grep -n 'stale-index' .forge/skills/lint/SKILL.md`
Expected: one match in the rule table.

- [ ] **Step 4: Commit**

```bash
git add .forge/skills/lint/SKILL.md
git commit -m "docs: document stale-index rule in lint skill

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Add the index-refresh step to the ingest skill

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md`

- [ ] **Step 1: Rewrite the "Update meta files" step**

In `.forge/skills/ingest/SKILL.md`, replace the entire `### 7. Update meta files`
section:

```
### 7. Update meta files

- Append entries to `wiki/index.md` for any new pages you created. (Or run `python3 .forge/lib/lint.py --fix` at the end to rebuild it.)
- Append to `wiki/log.md`: `## [YYYY-MM-DD] ingest | <source-slug>` plus a one-line note.
```

with:

```
### 7. Update meta files

- Append to `wiki/log.md`: `## [YYYY-MM-DD] ingest | <source-slug>` plus a one-line note.
- Regenerate the wiki index. Running `python3 .forge/lib/lint.py --fix` is the
  recommended close-out: it rebuilds both `wiki/index.md` and the `wiki/.meta/`
  index that `query` reads. (If you only need the `.meta/` index refreshed and
  not `index.md`, `python3 .forge/lib/index.py` does just that.) This is not
  optional — pages you ingested are not searchable until the index is rebuilt.
```

- [ ] **Step 2: Verify**

Run: `grep -n 'index.py\|--fix' .forge/skills/ingest/SKILL.md`
Expected: the new step 7 references both `lint.py --fix` and `.forge/lib/index.py`.

- [ ] **Step 3: Commit**

```bash
git add .forge/skills/ingest/SKILL.md
git commit -m "docs: ingest regenerates the wiki index as its close-out step

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Wire the feedback loop into the explorer skill

**Files:**
- Modify: `.forge/skills/explorer/SKILL.md`

- [ ] **Step 1: Update the signal-source count**

In `.forge/skills/explorer/SKILL.md`, in the `### 1. Identify candidate sources`
section, replace:

```
Three signal sources, in priority order:
```

with:

```
Four signal sources, in priority order:
```

- [ ] **Step 2: Add the fourth signal source**

Immediately after signal source **(c) Citation chains** (the paragraph that ends
`This count is the **co-citation score**.`) and before `### 2. Plan a bounded
slate`, insert:

```
**d) Curator query gaps.** Read `.forge/feedback.md` if it exists. The `query`
skill appends a `query-gap` entry there whenever the wiki could not answer a
question. Each entry is tagged `severity: hard` (no page covered it) or
`severity: weak` (answered only from `low`/`placeholder` pages). **Always
eligible.** Skip any entry whose question already appears in a prior
`## explorer plan` block in `.forge/log.md` — it has been slated before.
```

- [ ] **Step 3: Add the two scoring rows**

In the **Scoring** table, add these two rows immediately after the
`Named in consumer feedback.md` row:

```
| Named in a `query-gap` entry, `severity: hard`                           | 70    |
| Named in a `query-gap` entry, `severity: weak`                           | 25    |
```

- [ ] **Step 4: Verify**

Run: `grep -n 'query-gap\|Four signal' .forge/skills/explorer/SKILL.md`
Expected: matches for the new signal source paragraph and both scoring rows.

- [ ] **Step 5: Commit**

```bash
git add .forge/skills/explorer/SKILL.md
git commit -m "feat: explorer harvests query-gap entries from .forge/feedback.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Rewrite the query skill

**Files:**
- Modify: `.forge/skills/query/SKILL.md`

- [ ] **Step 1: Replace the entire file**

Overwrite `.forge/skills/query/SKILL.md` with:

````markdown
---
name: wikiforge-query
description: Answer a question from wiki content, citing pages by [[wikilink]]. Reads the wiki/.meta/ index; never writes wiki pages. Records unanswerable questions to .forge/feedback.md.
---

# query — wiki → answer

You have been asked a question. Answer it **from the wiki**, citing the pages
you used.

## Principle: answer from the wiki, not from memory

The point of this skill is a *grounded* answer — built from wiki pages whose
provenance you can name — rather than parametric recall mixed with
hallucination. The wiki is the input, not a hint. If a statement in your answer
is not supported by a wiki page you can cite, it does not belong in a `query`
answer. A question the wiki cannot support is not something you improvise around;
it is a gap you record (step 6).

`query` is **read-only over the wiki**. It never creates or edits wiki pages and
never writes the index. Its one and only write is an append to
`.forge/feedback.md`.

## Workflow

### 1. Orient

The `bin/wiki-*` scripts read a prebuilt index at `wiki/.meta/`. Read the
manifest:

```sh
bin/wiki-manifest
```

If a `bin/wiki-*` command reports `no wiki/.meta/...`, or a recent `lint` run
reported a `stale-index` warning, the index is missing or stale. **Stop** — do
not write the index yourself. Ask for it to be refreshed:

```sh
python3 .forge/lib/lint.py --fix      # rebuilds index.md and wiki/.meta/
```

Then re-run `bin/wiki-manifest`. Skim the top topics and `wiki/out_of_scope.md`.
Is the question in scope? If it falls under an explicit exclusion, say so and
stop — that is a correct answer, not a gap.

### 2. Search

```sh
bin/wiki-search <terms>
bin/wiki-search --type claim <terms>     # narrow to one page type
```

`--type` accepts any of the six page types: `concept`, `convention`,
`code-pattern`, `claim`, `source`, `entity`. Results rank title > tag > body
matches; `--n N` caps the count (default 10).

To browse rather than search:

```sh
bin/wiki-list --type concept             # every concept page
bin/wiki-list --tag optimization         # every page carrying a tag
```

### 3. Read

For each candidate (top 3–5):

```sh
bin/wiki-read <slug>
```

Pay attention to:
- The frontmatter `confidence:` field — `verified` and `likely` are strong;
  `low` and `placeholder` are weak; `refuted` means the page documents
  something that has been disproved.
- The appended **Backlinks** block — typed backlinks (`contradicts:`,
  `supersedes:`) are load-bearing context.
- For `claims/` pages, the `evidence:` and `counter_evidence:` lists name
  `sources/` pages you can also read.

To inspect one relationship sharply:

```sh
bin/wiki-backlinks --type contradicts <slug>   # what disputes this page
bin/wiki-backlinks --type supersedes <slug>    # what replaces it
```

### 4. Follow & corroborate

Follow `[[wikilinks]]` in prose when they are load-bearing for the answer — do
not follow exhaustively; stop when you have enough. Prefer a **corroborated**
answer: where two or more pages (or a page plus its `evidence:` sources) agree,
say so. Where the answer rests on a single page, say *that* too — single-source
is not wrong, but the reader deserves to know.

### 5. Synthesize

Write the answer. **Cite every claim** with the source page's wikilink
(`[[concepts/foo]]`, `[[claims/bar]]`). Quote a `code-patterns/` page when
implementation matters, and point the reader at `wiki/snippets/<slug>.txt` for
the code itself. If the most relevant page is `confidence: low` or
`placeholder`, the answer must say so — never launder a weak page into a
confident answer.

### 6. Record the gap

If the wiki could not fully answer the question, append an entry to
`.forge/feedback.md` so the `explorer` and `ingest` skills can close the gap. If
the file does not exist, create it with this header line first:

```
# .forge/feedback.md — append-only curator feedback log
```

Then append one entry. Two severities:

**`hard`** — no wiki page covers the question, or every relevant page is out of
scope:

```
## [2026-05-20T14:03:00Z] query-gap | severity: hard
Q: How does X handle Y?
No page covers this. Suggest ingesting: <topic or named source>.
```

**`weak`** — you answered, but only from `low`/`placeholder` pages:

```
## [2026-05-20T14:07:00Z] query-gap | severity: weak
Q: What is Z?
Answered from [[concepts/z]] (confidence: low). Needs a corroborating source.
```

Use a UTC ISO-8601 timestamp. One entry per unanswerable or weakly-answered
question. The file is **append-only** — never edit or delete prior entries. The
`explorer` skill harvests it; a `hard` gap scores as high as real consumer
feedback.

## Worked example — an answerable question

> *"What optimizer does the wiki recommend for sparse gradients?"*

```sh
bin/wiki-manifest                        # in scope: optimization is a top topic
bin/wiki-search sparse gradient
#   [1] concepts/optimization/adagrad (title)
#   [3] concepts/optimization/sgd (body)
bin/wiki-read concepts/optimization/adagrad
#   confidence: verified; Backlinks shows [[claims/adagrad-sparse-strong]] (extends)
bin/wiki-read claims/adagrad-sparse-strong
#   confidence: likely; evidence: [[sources/duchi-2011]]
```

Answer: *"For sparse gradients the wiki recommends AdaGrad
([[concepts/optimization/adagrad]]) — its per-parameter learning rates adapt to
feature frequency. [[claims/adagrad-sparse-strong]] supports this, citing
[[sources/duchi-2011]]. (One primary source — `likely`, not `verified`.)"*

No `.forge/feedback.md` entry: the wiki answered.

## Worked example — a hard gap

> *"What's the wiki's take on the Lion optimizer?"*

```sh
bin/wiki-search lion optimizer           # no results
bin/wiki-search --type claim lion        # no results
```

The wiki has nothing. Answer honestly: *"The wiki has no page on the Lion
optimizer. I won't answer from memory — I've recorded the gap."* Then append to
`.forge/feedback.md`:

```
## [2026-05-20T15:20:00Z] query-gap | severity: hard
Q: What is the wiki's assessment of the Lion optimizer?
No page covers this. Suggest ingesting: the Lion paper (Chen et al. 2023,
"Symbolic Discovery of Optimization Algorithms").
```

## What query is **not**

- Not a paraphrasing service. If a page says it well, quote it (with a
  wikilink) rather than rewriting.
- Not a research session. If answering needs sources the wiki lacks, record the
  gap (step 6) — do not fetch. That is the `explorer` skill's job.
- Not a place to lower the bar. A `low`-confidence answer is reported as a
  `low`-confidence answer.
- Not a writer of wiki pages or the index. The only file `query` writes is
  `.forge/feedback.md`.
````

- [ ] **Step 2: Verify**

Run: `grep -n 'feedback.md\|read-only over the wiki\|severity: hard' .forge/skills/query/SKILL.md`
Expected: matches for the principle, the read-only statement, and the gap format.

- [ ] **Step 3: Commit**

```bash
git add .forge/skills/query/SKILL.md
git commit -m "docs: rewrite query SKILL.md — grounded answers and gap feedback

Adds the .meta/ orient step, the full read interface (wiki-list,
wiki-backlinks), worked examples, and the .forge/feedback.md gap
protocol. query is now a strict read-only consumer of the wiki.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Add the query integration runbook

**Files:**
- Create: `tests/INTEGRATION_query.md`

- [ ] **Step 1: Create the runbook**

Create `tests/INTEGRATION_query.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/INTEGRATION_query.md
git commit -m "test: add query skill integration runbook

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the full test suite**

Run: `python3 -m pytest -q`
Expected: PASS — all tests green, including the new `test_index.py` and the new
`test_lint.py` / `test_bootstrap.py` cases.

- [ ] **Confirm build.py still imports cleanly**

Run: `python3 -c "import sys; sys.path.insert(0, '.forge/lib'); import build, index, lint"`
Expected: no output, exit 0.

---

## Known issue (out of scope — flagged, not fixed)

`bin/wiki-search`'s `--type` filter has a latent bug: for **body-rank** matches
it searches the directory `wiki/<type>` using the singular type name (e.g.
`wiki/concept`), but the actual directory is plural (`wiki/concepts`). Title and
tag ranks filter correctly against the `pages.tsv` `type` column, so typed
search still returns title/tag hits — only body-rank hits are dropped under a
`--type` filter. Fixing it touches `bin/wiki-search`, a POSIX bundle script
outside this plan's scope. The `query` SKILL.md documents `--type` without
relying on body-rank type filtering. Recommend a separate small task.
```
