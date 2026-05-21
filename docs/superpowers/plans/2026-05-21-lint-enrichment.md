# Lint Skill Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the curator-side `lint` skill to sibling depth and wire it into the workspace — an agent-facing report file, a draft-aware strict gate, a `low-confidence` rule, and a fix for `index.md` drift.

**Architecture:** `lint.py` gains a derived report (`.forge/lint-report.md`) regenerated each run, learns that `draft: true` issues are non-blocking, and emits a `low-confidence` warning. `index.md` rendering moves into `index.py` so every index regeneration (ingest, `lint --fix`, build) stays consistent. The `lint` SKILL.md is rewritten; `explorer`/`ingest`/`schema.md`/templates are updated to match.

**Tech Stack:** Python 3 (stdlib only), pytest, POSIX shell, Markdown.

**Spec:** `docs/superpowers/specs/2026-05-21-lint-enrichment-design.md`

---

## File Structure

- `.forge/lib/index.py` — gains `write_index_md`; `main()` writes `index.md` too
- `.forge/lib/lint.py` — `Issue.draft`; `low-confidence`; `stale-index` covers `index.md`; `collect_gaps`; `write_report`; `--gap-days`; `fix()` delegates to `index`
- `.forge/lib/build.py` — renders bundle `index.md` via `index.write_index_md`; drops `index` from `SHIPPED_META`; `run_lint` ignores draft errors
- `.forge/skills/lint/SKILL.md` — full rewrite
- `.forge/skills/explorer/SKILL.md`, `.forge/skills/ingest/SKILL.md` — contract/close-out updates
- `schema.md` — `## Index artifacts` note
- `templates/.gitignore.tmpl`, `templates/CLAUDE.md.tmpl`, `templates/AGENTS.md.tmpl`, `templates/GEMINI.md.tmpl` — `.forge/lint-report.md`
- `tests/test_index.py`, `tests/test_lint.py` — new cases
- `tests/INTEGRATION_lint.md` — new manual runbook

---

## Task 1: `index.write_index_md` — index.py owns index.md

**Files:**
- Modify: `.forge/lib/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_index.py`:

```python
def test_write_index_md_groups_by_type(tmp_path):
    import datetime
    import index
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        "---\ntitle: SGD\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    pages = list(index.load_pages(wiki))
    index.write_index_md(wiki, pages, datetime.date(2026, 5, 21))
    txt = (wiki / "index.md").read_text(encoding="utf-8")
    assert "# Index" in txt
    assert "## concepts" in txt
    assert "[[concepts/sgd]] — SGD" in txt


def test_write_index_md_empty_type_renders_none(tmp_path):
    import datetime
    import index
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    index.write_index_md(wiki, [], datetime.date(2026, 5, 21))
    assert "_(none)_" in (wiki / "index.md").read_text(encoding="utf-8")


def test_index_main_writes_index_md(tmp_path, monkeypatch):
    import index
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        "---\ntitle: SGD\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["index", "--wiki", str(wiki)])
    index.main()
    assert (wiki / "index.md").exists()
    assert (wiki / ".meta" / "pages.tsv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_index.py -v`
Expected: the three new tests FAIL with `AttributeError: module 'index' has no attribute 'write_index_md'`.

- [ ] **Step 3: Add `write_index_md` to `index.py`**

In `.forge/lib/index.py`, add this function after `write_meta` (before `main`):

```python
def write_index_md(wiki_dir, pages, today):
    """Render wiki_dir/index.md: a catalog of all pages grouped by type.

    `pages` is an iterable of (slug, page_type, fm, body) tuples, as load_pages
    yields. Meta files (page_type None) are skipped.
    """
    by_type = {}
    for slug, page_type, fm, _ in pages:
        if page_type is None or not isinstance(fm, dict):
            continue
        by_type.setdefault(page_type, []).append((slug, fm.get("title", slug)))
    lines = [
        "---",
        "title: index",
        "type: index",
        f"created: {today.isoformat()}",
        f"last_verified: {today.isoformat()}",
        "---",
        "",
        "# Index",
        "",
        "Catalog of all pages, grouped by type. Rebuilt by `.forge/lib/index.py`.",
        "",
    ]
    for pt in S.PAGE_TYPES:
        lines.append(f"## {S.TYPE_DIRS[pt]}")
        lines.append("")
        entries = sorted(by_type.get(pt, []))
        if not entries:
            lines.append("_(none)_")
        else:
            for slug, title in entries:
                lines.append(f"- [[{slug}]] — {title}")
        lines.append("")
    (wiki_dir / "index.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8")
```

- [ ] **Step 4: Make `index.py main()` write `index.md`**

In `.forge/lib/index.py`, replace the body of `main()` from `pages = list(load_pages(wiki_dir))` onward with:

```python
    pages = list(load_pages(wiki_dir))
    meta_dir = wiki_dir / ".meta"
    write_meta(meta_dir, pages)
    write_index_md(wiki_dir, pages, datetime.date.today())
    n = sum(1 for _, pt, _, _ in pages if pt is not None)
    print(f"indexed {n} page(s) -> {meta_dir} + {wiki_dir / 'index.md'}")
```

- [ ] **Step 5: Update the module docstring**

In `.forge/lib/index.py`, change the docstring line `"""index.py — build the wiki/.meta/ index (pages.tsv, links.tsv).` to:

```python
"""index.py — build the wiki index: wiki/.meta/ (pages.tsv, links.tsv) and index.md.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_index.py -v`
Expected: PASS (all tests, new and pre-existing).

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/index.py tests/test_index.py
git commit -m "feat: index.py renders index.md, not just .meta/"
```

---

## Task 2: `lint.fix()` delegates index rebuild to `index.py`

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py` (existing `fix` tests must stay green)

- [ ] **Step 1: Replace `fix()` in `lint.py`**

In `.forge/lib/lint.py`, replace the entire `fix(wiki_dir, today)` function (currently ~lines 311-352) with:

```python
def fix(wiki_dir, today):
    """Conservative auto-fix: rebuild index.md and wiki/.meta/ from current
    pages, via index.py. Never deletes or mutates pages."""
    pages = list(index.load_pages(wiki_dir))
    index.write_index_md(wiki_dir, pages, today)
    print(f"rebuilt {wiki_dir / 'index.md'}")
    index.write_meta(wiki_dir / ".meta", pages)
    print(f"rebuilt {wiki_dir / '.meta'}")
```

- [ ] **Step 2: Run the existing fix tests**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k fix`
Expected: PASS — `test_fix_rebuilds_index_from_pages`, `test_fix_marks_empty_types_as_none`, `test_fix_regenerates_meta_index` all green (the rendered `index.md` content is unchanged).

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py
git commit -m "refactor: lint --fix delegates index rebuild to index.py"
```

---

## Task 3: `Issue.draft` — draft-page issues are non-blocking

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint.py`:

```python
def test_draft_page_error_is_non_blocking(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "wip.md").write_text(
        _page("title: WIP\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely\ndraft: true"
              "\n---\n\nA broken [[concepts/nonexistent]] link.\n"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    broken = [i for i in issues if i.code == "broken-wikilink"]
    assert broken, "the broken wikilink should still be reported"
    assert broken[0].draft is True
    assert broken[0].is_blocking() is False
    assert not any(i.is_blocking() for i in issues)


def test_non_draft_page_error_is_blocking(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "live.md").write_text(
        _page("title: Live\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"
              "\n---\n\nA broken [[concepts/nonexistent]] link.\n"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert any(i.is_blocking() for i in issues)
```

Note: `_page` wraps text in `---\n...\n---\n\nbody\n`; these two tests pass their own closing `---` and body, so the `draft: true` / `confidence: likely` line is the last frontmatter line — `_page` adds the leading `---` only. Verify the produced file has exactly one opening and one closing `---`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k "draft or blocking"`
Expected: FAIL with `AttributeError: 'Issue' object has no attribute 'draft'`.

- [ ] **Step 3: Add `draft` and `is_blocking` to `Issue`**

In `.forge/lib/lint.py`, replace the `Issue` class with:

```python
class Issue:
    __slots__ = ("severity", "code", "page", "message", "draft")

    def __init__(self, severity, code, page, message, draft=False):
        self.severity = severity
        self.code = code
        self.page = page
        self.message = message
        self.draft = draft

    def is_blocking(self):
        """An error on a non-draft page. Only blocking issues fail --strict."""
        return self.severity == ERROR and not self.draft

    def fmt(self):
        tag = " (draft)" if self.draft else ""
        return f"[{self.severity:<7}] {self.code:<32} {self.page}: {self.message}{tag}"
```

- [ ] **Step 4: Mark draft-page issues in `lint()`**

In `.forge/lib/lint.py`, inside `lint()`, after `incoming = {s: 0 for s in valid_slugs}` add:

```python
    draft_slugs = set()
```

In the main `for slug, md, fm, body in pages:` loop, immediately after the
`check_frontmatter(slug, page_type, fm, issues)` line add:

```python
        if fm.get("draft") is True:
            draft_slugs.add(slug)
```

Then, just before `return issues` at the end of `lint()`, add:

```python
    for i in issues:
        if i.page in draft_slugs:
            i.draft = True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: draft-page lint issues are non-blocking for --strict"
```

---

## Task 4: `build.py` — render bundle index.md, honor draft non-blocking

**Files:**
- Modify: `.forge/lib/build.py`

- [ ] **Step 1: Drop `index` from `SHIPPED_META`**

In `.forge/lib/build.py`, change:

```python
SHIPPED_META = {"manifest", "index", "out_of_scope"}
```

to:

```python
# meta files copied verbatim into the bundle. index.md is NOT here — it is
# rendered fresh by index.write_index_md so it reflects the shipped page set.
SHIPPED_META = {"manifest", "out_of_scope"}
```

- [ ] **Step 2: Make `run_lint` ignore draft-page errors**

In `.forge/lib/build.py`, in `run_lint`, change:

```python
    errs = [i for i in issues if i.severity == LINT.ERROR]
```

to:

```python
    errs = [i for i in issues if i.is_blocking()]
```

- [ ] **Step 3: Render the bundle `index.md`**

In `.forge/lib/build.py`, in `build()`, find the `print("==> indexing")` block:

```python
    print("==> indexing")
    index.write_pages_tsv(out_meta, kept)
    index.write_links_tsv(out_meta, kept, kept_slugs)
```

Replace it with:

```python
    print("==> indexing")
    index.write_index_md(out_wiki, kept, datetime.date.today())
    index.write_pages_tsv(out_meta, kept)
    index.write_links_tsv(out_meta, kept, kept_slugs)
```

- [ ] **Step 4: Verify build still runs end to end**

If a buildable curator workspace fixture exists, run a build and confirm
`dist/<name>-v.../wiki/index.md` exists and lists only shipped pages. If no
fixture exists, this is verified by the integration runbook (Task 13). Run the
full unit suite to confirm nothing regressed:

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/build.py
git commit -m "feat: build renders bundle index.md; draft errors do not abort build"
```

---

## Task 5: `low-confidence` warning rule

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint.py`:

```python
def test_low_confidence_warns(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "stub.md").write_text(
        _page("title: Stub\ntype: concept\ncreated: 2026-05-19\n"
              "last_verified: 2026-05-19\nconfidence: low"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    lc = [i for i in issues if i.code == "low-confidence"]
    assert lc and lc[0].severity == lint.WARNING


def test_fresh_placeholder_is_low_confidence_not_rotting(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "ph.md").write_text(
        _page("title: PH\ntype: concept\ncreated: 2026-05-19\n"
              "last_verified: 2026-05-19\nconfidence: placeholder"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    codes = {i.code for i in issues}
    assert "low-confidence" in codes
    assert "placeholder-rotting" not in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k low_confidence`
Expected: FAIL — no `low-confidence` issue produced.

- [ ] **Step 3: Add the rule**

In `.forge/lib/lint.py`, in `lint()`, inside the main page loop, immediately
after the `# placeholder-rotting` block (the `if fm.get("confidence") == "placeholder":` block ending with the `placeholder-rotting` Issue), add:

```python
        # low-confidence
        if fm.get("confidence") in ("low", "placeholder"):
            issues.append(Issue(WARNING, "low-confidence", slug,
                f"confidence is {fm.get('confidence')!r}"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: add low-confidence lint warning"
```

---

## Task 6: `stale-index` also covers `index.md`

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py` (one existing test must be updated)

- [ ] **Step 1: Update the existing `stale-index` test that will break**

In `tests/test_lint.py`, the test `test_stale_index_silent_when_meta_fresh`
creates a fresh `.meta/pages.tsv` but no `index.md`; once `stale-index` also
checks `index.md`, it would fail. Update it so a fresh `index.md` is created
too. Replace the body of `test_stale_index_silent_when_meta_fresh` so that,
after writing `pages.tsv` and before the `os.utime` call, it also writes and
future-stamps `index.md`:

```python
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
    index_md = wiki / "index.md"
    index_md.write_text("# Index\n", encoding="utf-8")
    future = time.time() + 10
    os.utime(pages_tsv, (future, future))
    os.utime(index_md, (future, future))  # index.md newer than the page
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert not any(i.code == "stale-index" for i in issues)
```

- [ ] **Step 2: Write the new failing test**

Append to `tests/test_lint.py`:

```python
def test_stale_index_warns_when_index_md_stale(tmp_path):
    import os
    import time
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    page = wiki / "concepts" / "sgd.md"
    page.write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    meta = wiki / ".meta"
    meta.mkdir()
    pages_tsv = meta / "pages.tsv"
    pages_tsv.write_text("path\ttitle\ttype\ttags\tlast_verified\tconfidence\n",
                         encoding="utf-8")
    index_md = wiki / "index.md"
    index_md.write_text("# Index\n", encoding="utf-8")
    future = time.time() + 100
    os.utime(pages_tsv, (future, future))   # .meta fresh
    past = time.time() - 100
    os.utime(index_md, (past, past))        # index.md stale
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    stale = [i for i in issues if i.code == "stale-index"]
    assert any("index.md" in i.page for i in stale)
```

- [ ] **Step 3: Run tests to verify the new one fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k stale_index`
Expected: `test_stale_index_warns_when_index_md_stale` FAILS; the other stale-index tests PASS.

- [ ] **Step 4: Extend `check_stale_index`**

In `.forge/lib/lint.py`, replace the entire `check_stale_index` function with:

```python
def check_stale_index(wiki_dir, issues):
    """Warn if wiki/.meta/pages.tsv or wiki/index.md is missing or older than
    the newest wiki page."""
    newest = 0.0
    for md in wiki_dir.rglob("*.md"):
        if ".meta" in md.parts:
            continue
        newest = max(newest, md.stat().st_mtime)
    remedy = "run python3 .forge/lib/lint.py --fix"
    meta = wiki_dir / ".meta" / "pages.tsv"
    if not meta.exists():
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            f"wiki/.meta/ index missing — {remedy}"))
    elif meta.stat().st_mtime < newest:
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            f"index older than newest wiki page — {remedy}"))
    index_md = wiki_dir / "index.md"
    if not index_md.exists():
        issues.append(Issue(WARNING, "stale-index", "index.md",
            f"wiki/index.md missing — {remedy}"))
    elif index_md.stat().st_mtime < newest:
        issues.append(Issue(WARNING, "stale-index", "index.md",
            f"index.md older than newest wiki page — {remedy}"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: stale-index rule also catches a stale index.md"
```

---

## Task 7: `collect_gaps` — read query-gaps from feedback.md

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint.py`:

```python
def test_collect_gaps_window_filter(tmp_path):
    feedback = tmp_path / "feedback.md"
    feedback.write_text(
        "# feedback.md\n\n"
        "## [2026-05-19T10:00:00Z] query-gap | severity: hard\n"
        "Q: Recent question?\n"
        "No page covers this.\n\n"
        "## [2025-01-01T10:00:00Z] query-gap | severity: weak\n"
        "Q: Old question?\n"
        "Answered from a low page.\n",
        encoding="utf-8")
    gaps = lint.collect_gaps(feedback, 90, datetime.date(2026, 5, 20))
    assert len(gaps) == 1
    assert gaps[0]["severity"] == "hard"
    assert gaps[0]["lines"][0] == "Q: Recent question?"


def test_collect_gaps_missing_file(tmp_path):
    assert lint.collect_gaps(tmp_path / "nope.md", 90, datetime.date(2026, 5, 20)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k collect_gaps`
Expected: FAIL with `AttributeError: module 'lint' has no attribute 'collect_gaps'`.

- [ ] **Step 3: Add `collect_gaps` and `_gap_date`**

In `.forge/lib/lint.py`, add these two functions after `parse_date` (before `detect_type_from_slug`):

```python
def _gap_date(ts):
    """Parse an ISO-8601 timestamp from a query-gap header; None if unparseable."""
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def collect_gaps(feedback_path, gap_days, today):
    """Parse query-gap entries from .forge/feedback.md within `gap_days` of
    `today`. Returns dicts {ts, severity, lines}, newest first. An entry with an
    unparseable timestamp is kept (surfaced rather than silently dropped)."""
    if not feedback_path.exists():
        return []
    cutoff = today - datetime.timedelta(days=gap_days)
    gaps = []
    cur = None
    for line in feedback_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ") and "query-gap" in line:
            ts = ""
            lb, rb = line.find("["), line.find("]")
            if 0 <= lb < rb:
                ts = line[lb + 1:rb]
            sev = "unknown"
            if "severity:" in line:
                sev = line.split("severity:", 1)[1].strip()
            cur = {"ts": ts, "severity": sev, "lines": []}
            gaps.append(cur)
        elif line.startswith("## "):
            cur = None
        elif cur is not None and line.strip():
            cur["lines"].append(line.rstrip())
    kept = []
    for g in gaps:
        d = _gap_date(g["ts"])
        if d is None or d >= cutoff:
            kept.append(g)
    kept.sort(key=lambda g: g["ts"], reverse=True)
    return kept
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k collect_gaps`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: lint reads query-gaps from .forge/feedback.md"
```

---

## Task 8: `write_report` + `--gap-days` — the agent-facing report

**Files:**
- Modify: `.forge/lib/lint.py`
- Test: `tests/test_lint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint.py`:

```python
def test_write_report_sections(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "live.md").write_text(
        _page("title: Live\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: low"
              "\n---\n\nBroken [[concepts/missing]].\n"),
        encoding="utf-8")
    (wiki / "concepts" / "wip.md").write_text(
        _page("title: WIP\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely\ndraft: true"
              "\n---\n\nBroken [[concepts/alsomissing]].\n"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    gaps = [{"ts": "2026-05-19T10:00:00Z", "severity": "hard",
             "lines": ["Q: Something?"]}]
    report = tmp_path / "lint-report.md"
    lint.write_report(report, issues, gaps, datetime.date(2026, 5, 20))
    txt = report.read_text(encoding="utf-8")
    assert "# Lint report" in txt
    assert "## Errors" in txt
    assert "## Warnings" in txt
    assert "low-confidence" in txt
    assert "## Draft pages" in txt
    assert "[[concepts/wip]]" in txt
    assert "## Open knowledge gaps" in txt
    assert "Q: Something?" in txt


def test_main_writes_report(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "ws"
    wiki = workspace / "wiki"
    forge = workspace / ".forge"
    (wiki / "concepts").mkdir(parents=True)
    forge.mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lint", "--report",
                                     "--wiki", str(wiki), "--raw", str(workspace / "raw")])
    lint.main()
    assert (forge / "lint-report.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v -k "report"`
Expected: `test_write_report_sections` and `test_main_writes_report` FAIL (`write_report` missing / no report file).

- [ ] **Step 3: Add `write_report`**

In `.forge/lib/lint.py`, add this function after `collect_gaps`:

```python
def write_report(report_path, issues, gaps, today):
    """Render the agent-facing health snapshot to report_path. Overwrites."""
    errors = [i for i in issues if i.severity == ERROR and not i.draft]
    warnings = [i for i in issues if i.severity == WARNING and not i.draft]
    draft_issues = [i for i in issues if i.draft]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    out = ["# Lint report", "",
           f"Generated {stamp} · {len(errors)} error(s), {len(warnings)} warning(s)",
           "", "## Errors", ""]
    if errors:
        for i in sorted(errors, key=lambda i: (i.code, i.page)):
            out.append(f"[{i.code}] {i.page}: {i.message}")
    else:
        out.append("_(none)_")
    out += ["", "## Warnings", ""]
    by_code = {}
    for i in warnings:
        by_code.setdefault(i.code, []).append(i)
    if by_code:
        for code in sorted(by_code):
            items = by_code[code]
            out.append(f"### {code} ({len(items)})")
            for i in sorted(items, key=lambda i: i.page):
                out.append(f"- [[{i.page}]] — {i.message}")
            out.append("")
    else:
        out += ["_(none)_", ""]
    out += ["## Draft pages", "",
            "Pages with `draft: true` — excluded from the build and from "
            "`--strict`. Their issues are advisory; resolve before un-drafting.",
            ""]
    draft_by_page = {}
    for i in draft_issues:
        draft_by_page.setdefault(i.page, []).append(i.code)
    if draft_by_page:
        for page in sorted(draft_by_page):
            codes = ", ".join(sorted(set(draft_by_page[page])))
            out.append(f"- [[{page}]] — {len(draft_by_page[page])} issue(s): {codes}")
    else:
        out.append("_(none)_")
    out += ["", "## Open knowledge gaps", "",
            "`query-gap` entries from `.forge/feedback.md`, newest first.", ""]
    if gaps:
        for g in gaps:
            summary = g["lines"][0] if g["lines"] else ""
            out.append(f"- [{g['ts']}] severity: {g['severity']} — {summary}")
    else:
        out.append("_(none)_")
    report_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
```

- [ ] **Step 4: Add `--gap-days` and wire report writing into `main()`**

In `.forge/lib/lint.py`, in `main()`, after the line
`p.add_argument("--rot-days", type=int, default=S.PLACEHOLDER_ROT_DAYS)` add:

```python
    p.add_argument("--gap-days", type=int, default=90,
                   help="knowledge-gap window for the report (default: 90)")
```

Then, in `main()`, after the issues are printed and counted (after the
`print(f"\n{n_err} error(s), {n_warn} warning(s)", file=sys.stderr)` line and
before the `if args.strict` block), add:

```python
    # agent-facing report — written for report/strict runs, not --fix
    forge_dir = wiki_dir.parent / ".forge"
    if forge_dir.is_dir():
        gaps = collect_gaps(forge_dir / "feedback.md", args.gap_days, today)
        write_report(forge_dir / "lint-report.md", issues, gaps, today)
```

- [ ] **Step 5: Make `--strict` exit only on blocking errors**

In `.forge/lib/lint.py`, in `main()`, the strict exit currently reads:

```python
    if args.strict and n_err > 0:
        sys.exit(1)
```

Change `n_err` so it counts only blocking errors. Replace the counting lines:

```python
    n_err = sum(1 for i in issues if i.severity == ERROR)
    n_warn = len(issues) - n_err
```

with:

```python
    n_err = sum(1 for i in issues if i.is_blocking())
    n_warn = sum(1 for i in issues if i.severity == WARNING)
```

(The strict-exit `if args.strict and n_err > 0` line stays as is.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest tests/test_lint.py -v`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat: lint writes .forge/lint-report.md health snapshot"
```

---

## Task 9: Rewrite `lint/SKILL.md` to sibling depth

**Files:**
- Modify: `.forge/skills/lint/SKILL.md` (full rewrite)

- [ ] **Step 1: Rewrite the skill**

Replace the entire contents of `.forge/skills/lint/SKILL.md` with the document
below. It keeps the `name`/`description` frontmatter shape of the siblings,
adds the `low-confidence` row, the report-file section, the draft section, and
a worked example.

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/skills/lint/SKILL.md
git commit -m "docs: rewrite lint SKILL.md — report file, draft pages, worked example"
```

---

## Task 10: Update `explorer/SKILL.md` to read the report file

**Files:**
- Modify: `.forge/skills/explorer/SKILL.md`

- [ ] **Step 1: Replace the lint signal source in step 1(a)**

In `.forge/skills/explorer/SKILL.md`, find subsection **a) Lint errors and
warnings** under `### 1. Identify candidate sources`. Replace its body (the
````sh ... ```` block and the `Look for:` list) with:

````markdown
**a) Lint errors and warnings.** Refresh and read the lint report:

```sh
python3 .forge/lib/lint.py --report >/dev/null
cat .forge/lint-report.md
```

Harvest the **mechanical** signals from the report's `## Errors` and
`## Warnings` sections:
- `code-pattern-missing-provenance` / `excerpt-missing` — the cited repo isn't
  in `raw/repos/`. **High priority** — concrete, named gaps.
- `low-confidence` — pages whose `confidence:` is `low` or `placeholder`. Each
  needs a stronger or second source.
- `stale` — pages overdue for re-verification against their source.
- `orphan` clusters — may need supporting sources (often LOW priority; an
  orphan is sometimes just stylistic).

Do **not** harvest the report's `## Open knowledge gaps` section here — those
`query-gap` entries are picked up directly from `.forge/feedback.md` in
signal (d) below. Reading them from both places would double-count.
````

- [ ] **Step 2: Verify the scoring table still matches**

In `.forge/skills/explorer/SKILL.md`, confirm the scoring table under
`### 2. Plan a bounded slate` already has a row
`Adds a second source for a `low-confidence` page` (score 25) and a
`Closes an `orphan` warning` row (score 15). It does — no change needed. If a
`stale` row is absent, add this row to the table after the `low-confidence` row:

```markdown
| Re-verifies a `stale` page against its source                            | 20    |
```

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/skills/explorer/SKILL.md
git commit -m "docs: explorer reads .forge/lint-report.md for mechanical signals"
```

---

## Task 11: Update `ingest/SKILL.md` and `schema.md`

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md`
- Modify: `schema.md`

- [ ] **Step 1: Fix the stale `index.py` note in ingest SKILL.md**

In `.forge/skills/ingest/SKILL.md`, the index close-out step says `index.py`
refreshes only `.meta/` and not `index.md`. That parenthetical is now wrong —
`index.py` writes both. Find the sentence containing
`If you only need the \`.meta/\` index refreshed and not \`index.md\`` and
replace the full parenthetical
`(If you only need the \`.meta/\` index refreshed and not \`index.md\`, \`python3 .forge/lib/index.py\` does just that.)`
with:

```markdown
(`python3 .forge/lib/index.py` does the same index rebuild — both `index.md`
and `wiki/.meta/` — without running the lint checks.)
```

- [ ] **Step 2: Note the report file in ingest's lint close-out**

In `.forge/skills/ingest/SKILL.md`, under `## Lint before you stop`, after the
`python3 .forge/lib/lint.py --report` code block, add this sentence:

```markdown
That run also refreshes `.forge/lint-report.md` — the health snapshot the next
`explorer` pass reads.
```

- [ ] **Step 3: Update `schema.md` Index artifacts section**

In `schema.md`, under `## Index artifacts`, replace the first paragraph:

```markdown
Two TSV files in `wiki/.meta/` index the wiki. They are produced by
`.forge/lib/index.py` — invoked on demand in the curator workspace (by `ingest`
after a run and by `lint --fix`) and by `build.py` when assembling a bundle. The
curator-side index covers every page; the bundle-side index covers only the
pages that ship.
```

with:

```markdown
`.forge/lib/index.py` produces the wiki's derived index: two TSV files in
`wiki/.meta/` (consumed by the `bin/wiki-*` read scripts) and `wiki/index.md`
(the human/agent catalog page). It is invoked on demand in the curator
workspace (by `ingest` after a run and by `lint --fix`) and by `build.py` when
assembling a bundle. The curator-side index covers every page; the bundle-side
index covers only the pages that ship.
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add .forge/skills/ingest/SKILL.md schema.md
git commit -m "docs: index.py owns index.md; ingest refreshes the lint report"
```

---

## Task 12: Template updates — gitignore and agent guides

**Files:**
- Modify: `templates/.gitignore.tmpl`
- Modify: `templates/CLAUDE.md.tmpl`, `templates/AGENTS.md.tmpl`, `templates/GEMINI.md.tmpl`

- [ ] **Step 1: Add the report to `.gitignore.tmpl`**

In `templates/.gitignore.tmpl`, find the block:

```
# derived wiki index — regenerated by .forge/lib/index.py
wiki/.meta/
```

and append directly after it:

```
# derived lint health snapshot — regenerated on every lint run
.forge/lint-report.md
```

- [ ] **Step 2: Add the report to the `.forge/` tree in `CLAUDE.md.tmpl`**

In `templates/CLAUDE.md.tmpl`, in the "What lives where" tree, find the line:

```
  feedback.md          # query-gap log; harvested by explorer
```

and add directly after it:

```
  lint-report.md       # derived health snapshot; regenerated each lint run
```

Do **not** add `lint-report.md` to the append-only-state hard rule (rule 6) —
it is overwritten each run, not appended.

- [ ] **Step 3: Apply the same tree edit to `AGENTS.md.tmpl` and `GEMINI.md.tmpl`**

Open `templates/AGENTS.md.tmpl` and `templates/GEMINI.md.tmpl`. In each, locate
the `.forge/` directory tree (search for `feedback.md`). If a `feedback.md` line
exists, add a `lint-report.md` line after it, matching that file's existing
indentation and comment style:

```
  lint-report.md       # derived health snapshot; regenerated each lint run
```

If a template has no `.forge/` tree or no `feedback.md` line, make no change to
that file (record which files were changed in the commit message).

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add templates/.gitignore.tmpl templates/CLAUDE.md.tmpl templates/AGENTS.md.tmpl templates/GEMINI.md.tmpl
git commit -m "docs: templates document .forge/lint-report.md"
```

---

## Task 13: Integration runbook — `tests/INTEGRATION_lint.md`

**Files:**
- Create: `tests/INTEGRATION_lint.md`

- [ ] **Step 1: Create the runbook**

Write `tests/INTEGRATION_lint.md` with exactly this content:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
cd /home/ubuntu/workspace/WikiForge
git add tests/INTEGRATION_lint.md
git commit -m "test: add lint skill integration runbook"
```

---

## Task 14: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire unit suite**

Run: `cd /home/ubuntu/workspace/WikiForge && python3 -m pytest -v`
Expected: PASS — every test in `tests/`, including `test_index.py`,
`test_lint.py`, and the pre-existing `test_build.py`-adjacent suites.

- [ ] **Step 2: Exercise the lint CLI against the live workspace**

Run each and confirm behavior:

```sh
cd /home/ubuntu/workspace/WikiForge
python3 .forge/lib/lint.py --report   # exits 0, prints issues
python3 .forge/lib/lint.py --fix      # rebuilds index.md + wiki/.meta/
python3 .forge/lib/index.py           # rebuilds index.md + wiki/.meta/
```

Expected: no tracebacks. After `--report`, if a `wiki/` and `.forge/` exist,
`.forge/lint-report.md` is present and well-formed. (If this framework repo has
no `wiki/` dir, the CLI prints `lint: wiki dir not found` and exits 1 — that is
correct; the runbook in Task 13 covers a real curator workspace.)

- [ ] **Step 3: Confirm the manual runbook is followed at least once**

Walk `tests/INTEGRATION_lint.md` Checks 1–7 in a curator workspace (or note in
the final report that no curator workspace is available in this repo and the
runbook is deferred to first `wf init` use).

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
cd /home/ubuntu/workspace/WikiForge
git add -A
git commit -m "test: verify lint enrichment end to end"
```

(Skip this commit if Steps 1–3 required no changes.)

---

## Self-Review Notes

- **Spec coverage:** Component A → Tasks 7, 8, 12, 13. Component B → Tasks 3, 4.
  Component C → Task 5. Component D → Tasks 1, 2, 4, 6. Component E → Task 9.
  Component F → Task 10. Cross-cutting → Tasks 11, 12. Testing → every code task
  is TDD; Task 13 adds the runbook; Task 14 verifies.
- **Type consistency:** `Issue.draft` (bool), `Issue.is_blocking()` (method),
  `index.write_index_md(wiki_dir, pages, today)`, `lint.collect_gaps(path, gap_days, today)`,
  `lint.write_report(report_path, issues, gaps, today)` — names used identically
  across Tasks 1–8 and the SKILL.md prose.
- **Known existing-test impact:** `test_stale_index_silent_when_meta_fresh` is
  updated in Task 6 Step 1 (it would otherwise break on the new `index.md`
  check). The three `fix` tests in `test_lint.py` are confirmed green in Task 2.
</content>
