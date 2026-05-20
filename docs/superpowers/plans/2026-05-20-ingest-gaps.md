# Ingest Skill Gap-Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the seven gaps in WikiForge's `ingest` skill (Phase 5) — robust queue helpers, raw-source scanning, dedup lookup, format normalization (MinerU/Tavily/markdownify), credential handling, and a schema cheatsheet — and add a credentials-collection stage to the bootstrap workflow.

**Architecture:** Ingest gains a *normalization layer*: each queued source is converted to markdown by `normalize.py`, which routes by file type to MinerU (PDF/Office), `markdownify` (HTML), or the Tavily CLI (URLs). Converted output lands in a sibling `<stem>.converted/` directory; the original raw file is never modified. Tool credentials (`MINERU_API_TOKEN`, `TAVILY_API_KEY`, plus arbitrary future keys) live in a gitignored `.forge/secrets/credentials.env`, collected by a new optional bootstrap step and loaded into the environment by `credentials.py`. The mechanical helpers ingest already relies on (`ingest_helpers.py`) are made crash-safe and gain `scan_raw()` and `find_ingested_source()`.

**Tech Stack:** Python 3 (curator-side, stdlib + `pyyaml` + `markdownify`), `pytest` for tests, MinerU API (vendored `mineru_api.py`, stdlib-only), Tavily CLI (`tvly`), POSIX shell for the bootstrap runbook.

---

## Source-type → tool reference

This table is the design answer to "what tools are needed for each `raw/` style." It is implemented by `normalize.py` (Tasks 7-9) and documented in the ingest `SKILL.md` (Task 12).

| `raw/` subdir | Artifact formats        | Normalization tool                         | Credential        |
| ------------- | ----------------------- | ------------------------------------------ | ----------------- |
| `raw/papers/` | `.pdf`                  | MinerU (`.forge/lib/mineru_api.py`)         | `MINERU_API_TOKEN` (optional; free tier 10MB/20pp) |
| `raw/docs/`   | `.pdf .docx .pptx .xls .xlsx` | MinerU                               | `MINERU_API_TOKEN` (optional) |
| `raw/web/`    | `.html .htm`            | `markdownify` (offline, local)              | none              |
| `raw/web/`    | `.url .weblink` (file holding a URL) | Tavily CLI `tvly extract`      | `TAVILY_API_KEY`  |
| `raw/notes/`  | `.md .markdown .txt`    | none — already readable                     | none              |
| `raw/repos/`  | `<org>/<repo>@<sha>/` directory | none — read files directly via `enumerate_repo_files` | none (public repos only in v1) |

The credentials file is an open `KEY=value` list, so future tools (audio transcription, OCR services) need only a new line — no code change.

## File structure

**New files:**
- `.forge/lib/mineru_api.py` — vendored MinerU PDF/Office→markdown converter (stdlib-only; runs as a subprocess).
- `.forge/lib/normalize.py` — normalization dispatcher: raw artifact → markdown in a sibling `.converted/` dir.
- `.forge/lib/credentials.py` — `load_credentials()`: parse `.forge/secrets/credentials.env`, inject into `os.environ`.
- `tests/conftest.py` — puts `.forge/lib/` on `sys.path` so tests can import the helper modules.
- `tests/test_ingest_helpers.py` — tests for the new/hardened `ingest_helpers` functions.
- `tests/test_credentials.py` — tests for `credentials.py`.
- `tests/test_normalize.py` — tests for `normalize.py` routing and conversion.
- `tests/test_bootstrap.py` — tests for the bootstrap credentials seeding.
- `tests/INTEGRATION_ingest.md` — manual Phase-5 integration runbook (the test PLAN_Init.md Phase 5 specifies).

**Modified files:**
- `.forge/lib/ingest_helpers.py` — crash-safe queue helpers; add `scan_raw()`, `find_ingested_source()`.
- `.forge/lib/bootstrap.py` — seed `.forge/secrets/credentials.env`.
- `.forge/skills/ingest/SKILL.md` — normalization step, MinerU/Tavily wiring, credentials note, frontmatter cheatsheet, log-path fix.
- `bootstrap.md` — new Step 8 (credentials); renumber Steps 8→9, 9→10, 10→11.
- `requirements.txt` — add `markdownify`, `pytest`.

---

### Task 1: Test scaffolding and dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add dependencies to `requirements.txt`**

Replace the file's contents with:

```
# Curator-side Python dependencies. Install with:
#   pip install -r requirements.txt
#
# Bundle consumers need none of this — the bundle is pure POSIX shell + markdown.

pyyaml>=6.0
markdownify>=0.11    # raw/web/*.html -> markdown, used by .forge/lib/normalize.py

# Development / tests only.
pytest>=7.0
```

- [ ] **Step 2: Install the dependencies**

Run: `pip install -r requirements.txt`
Expected: installs `markdownify` and `pytest` (and `pyyaml` if not present), exits 0.

- [ ] **Step 3: Create `tests/conftest.py`**

```python
"""pytest configuration: make the curator-side helper modules importable.

The WikiForge Python helpers live in .forge/lib/ (not a package on PYTHONPATH).
Tests import them by bare name (`import ingest_helpers`), so put that directory
on sys.path before collection.
"""
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / ".forge" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
```

- [ ] **Step 4: Verify pytest is wired up**

Run: `python3 -m pytest --version`
Expected: prints a `pytest 7.x` (or newer) version line, exits 0.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/conftest.py
git commit -m "test: add pytest scaffolding and markdownify dependency"
```

---

### Task 2: Make queue helpers crash-safe

The queue helpers in `ingest_helpers.py` call `Path(queue_path).read_text()` unconditionally. On a workspace whose `.forge/queue.md` is absent, `ingest --scan` crashes with `FileNotFoundError`. Make `parse_queue` tolerate a missing file, `append_queue_entry` create it, and `set_queue_state` fail with a clear error.

**Files:**
- Modify: `.forge/lib/ingest_helpers.py`
- Test: `tests/test_ingest_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest_helpers.py`:

```python
import pytest

import ingest_helpers as ih


def test_parse_queue_missing_file_returns_empty(tmp_path):
    assert list(ih.parse_queue(tmp_path / "nope.md")) == []


def test_append_queue_entry_creates_missing_file(tmp_path):
    q = tmp_path / "queue.md"
    created = ih.append_queue_entry(q, "raw/papers/a.pdf")
    assert created is True
    assert q.exists()
    assert q.read_text().startswith("# .forge/queue.md")
    entries = list(ih.parse_queue(q))
    assert len(entries) == 1
    assert entries[0][1] == " " and entries[0][2] == "raw/papers/a.pdf"


def test_set_queue_state_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ih.set_queue_state(tmp_path / "nope.md", "raw/x", "x")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_ingest_helpers.py -v`
Expected: FAIL — `test_parse_queue_missing_file_returns_empty` and `test_append_queue_entry_creates_missing_file` raise `FileNotFoundError`.

- [ ] **Step 3: Add a queue header constant and harden the three helpers**

In `.forge/lib/ingest_helpers.py`, add this constant just below the `QUEUE_ENTRY_RE` definition (after line 16):

```python
QUEUE_HEADER = (
    "# .forge/queue.md — append-only ingest queue\n"
    "<!-- See schema.md or .forge/skills/ingest/SKILL.md for entry format. -->\n"
    "<!-- States: [ ] pending  [~] in progress  [x] done  [!] blocked. -->\n"
)
```

Replace the body of `parse_queue` so the first lines become:

```python
def parse_queue(queue_path):
    """Yield (line_number, state, source_path, note) for each entry in queue.md.

    A missing queue file yields nothing (an un-bootstrapped or fresh workspace
    has no queue yet).
    """
    p = Path(queue_path)
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        m = QUEUE_ENTRY_RE.match(line.rstrip())
        if m:
            yield i, m.group("state"), m.group("path"), (m.group("note") or "").strip()
```

Replace the first lines of `append_queue_entry` (the `p = Path(...)` / `text = p.read_text(...)` pair) with:

```python
def append_queue_entry(queue_path, source_path, note=""):
    """Append a `[ ] <path> | <note>` line if not already present.

    Creates the queue file (with its standard header) if it does not exist.
    """
    p = Path(queue_path)
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(QUEUE_HEADER, encoding="utf-8")
    text = p.read_text(encoding="utf-8")
```

In `set_queue_state`, immediately after the `if new_state not in QUEUE_STATES:` raise block and before `p = Path(queue_path)` is dereferenced, add the missing-file guard. The function start becomes:

```python
def set_queue_state(queue_path, source_path, new_state, note=None):
    """Mutate an existing entry's state marker. new_state in QUEUE_STATES."""
    if new_state not in QUEUE_STATES:
        raise ValueError(f"invalid state {new_state!r}; must be one of {sorted(QUEUE_STATES)}")
    p = Path(queue_path)
    if not p.is_file():
        raise FileNotFoundError(f"queue file does not exist: {queue_path}")
    text = p.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ingest_helpers.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/ingest_helpers.py tests/test_ingest_helpers.py
git commit -m "fix: make ingest queue helpers crash-safe on a missing queue file"
```

---

### Task 2 produced `parse_queue`/`append_queue_entry`/`set_queue_state` hardened; Task 3 adds `scan_raw`

### Task 3: Add `scan_raw()` to enumerate raw sources

`ingest --scan` must walk `raw/` and find ingestable sources. There is no helper for this today. `scan_raw()` yields each candidate: recognized-extension files under `raw/{papers,docs,web,notes}/`, and each `raw/repos/<org>/<repo>@<sha>/` directory as a single unit. It excludes `.converted/` output directories and dotfiles (`.gitkeep`).

**Files:**
- Modify: `.forge/lib/ingest_helpers.py`
- Test: `tests/test_ingest_helpers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ingest_helpers.py`:

```python
def test_scan_raw_finds_files_and_repos(tmp_path):
    (tmp_path / "raw/papers").mkdir(parents=True)
    (tmp_path / "raw/papers/a.pdf").write_bytes(b"%PDF fake")
    (tmp_path / "raw/papers/.gitkeep").write_text("")
    (tmp_path / "raw/notes").mkdir(parents=True)
    (tmp_path / "raw/notes/n.md").write_text("note")
    (tmp_path / "raw/web").mkdir(parents=True)
    (tmp_path / "raw/web/page.html").write_text("<h1>x</h1>")
    repo = tmp_path / "raw/repos/acme/widget@abc123"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("readme")
    # a .converted output directory must be excluded entirely
    conv = tmp_path / "raw/papers/a.converted"
    conv.mkdir()
    (conv / "a.md").write_text("converted")

    found = {str(p) for p in ih.scan_raw(tmp_path)}

    assert str(tmp_path / "raw/papers/a.pdf") in found
    assert str(tmp_path / "raw/notes/n.md") in found
    assert str(tmp_path / "raw/web/page.html") in found
    assert str(repo) in found
    assert not any(".converted" in f for f in found)
    assert not any(".gitkeep" in f for f in found)
    # the repo's inner files are NOT yielded individually
    assert str(repo / "README.md") not in found
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_helpers.py::test_scan_raw_finds_files_and_repos -v`
Expected: FAIL — `AttributeError: module 'ingest_helpers' has no attribute 'scan_raw'`.

- [ ] **Step 3: Implement `scan_raw()`**

Add to `.forge/lib/ingest_helpers.py` (after `enumerate_repo_files`):

```python
RAW_FILE_TYPES = ("papers", "docs", "web", "notes")
SOURCE_EXTS = {
    ".pdf", ".docx", ".pptx", ".xls", ".xlsx",
    ".html", ".htm", ".url", ".weblink",
    ".md", ".markdown", ".txt",
}


def scan_raw(workspace_root="."):
    """Yield Paths of candidate raw sources under `raw/`.

    Files: any file with a recognized extension under raw/{papers,docs,web,
    notes}/ (recursively), skipping dotfiles and anything inside a `.converted/`
    output directory.

    Repos: each raw/repos/<org>/<repo>@<sha>/ directory, yielded whole — a repo
    is one ingestion unit, not a file-per-file scan.
    """
    root = Path(workspace_root)
    for rtype in RAW_FILE_TYPES:
        base = root / "raw" / rtype
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            rel_parts = f.relative_to(base).parts
            if any(part.startswith(".") or part.endswith(".converted")
                   for part in rel_parts):
                continue
            if f.suffix.lower() in SOURCE_EXTS:
                yield f
    repos_base = root / "raw" / "repos"
    if repos_base.is_dir():
        for org in sorted(d for d in repos_base.iterdir()
                          if d.is_dir() and not d.name.startswith(".")):
            for repo in sorted(d for d in org.iterdir()
                               if d.is_dir() and "@" in d.name):
                yield repo
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_helpers.py::test_scan_raw_finds_files_and_repos -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/ingest_helpers.py tests/test_ingest_helpers.py
git commit -m "feat: add scan_raw() to enumerate ingestable raw sources"
```

---

### Task 4: Add `find_ingested_source()` for dedup lookup

Ingest step 1 ("Check for prior ingestion") tells the agent to find a `wiki/sources/` page whose `content_hash:` matches. `content_hash()` exists but the lookup half does not. `find_ingested_source()` scans `wiki/sources/*.md` frontmatter and returns the matching page.

**Files:**
- Modify: `.forge/lib/ingest_helpers.py`
- Test: `tests/test_ingest_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingest_helpers.py`:

```python
def _write_source_page(dir_path, name, content_hash, source_path):
    page = dir_path / name
    page.write_text(
        "---\n"
        f"title: {name}\n"
        "type: source\n"
        "created: 2026-01-01\n"
        "last_verified: 2026-01-01\n"
        "confidence: likely\n"
        "source_type: paper\n"
        f"source_path: {source_path}\n"
        f"content_hash: {content_hash}\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )


def test_find_ingested_source_by_hash(tmp_path):
    src = tmp_path / "wiki/sources"
    src.mkdir(parents=True)
    _write_source_page(src, "foo.md", "sha256:abc123", "raw/papers/foo.pdf")
    hit = ih.find_ingested_source(tmp_path, content_hash="sha256:abc123")
    assert hit is not None
    slug, fm = hit
    assert slug == "sources/foo"
    assert fm["source_path"] == "raw/papers/foo.pdf"
    assert ih.find_ingested_source(tmp_path, content_hash="sha256:zzz") is None


def test_find_ingested_source_by_path(tmp_path):
    src = tmp_path / "wiki/sources"
    src.mkdir(parents=True)
    _write_source_page(src, "foo.md", "sha256:abc123", "raw/papers/foo.pdf")
    hit = ih.find_ingested_source(tmp_path, source_path="raw/papers/foo.pdf")
    assert hit is not None and hit[0] == "sources/foo"


def test_find_ingested_source_missing_dir(tmp_path):
    assert ih.find_ingested_source(tmp_path, content_hash="sha256:abc") is None


def test_find_ingested_source_requires_a_key(tmp_path):
    with pytest.raises(ValueError):
        ih.find_ingested_source(tmp_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_ingest_helpers.py -k find_ingested -v`
Expected: FAIL — `AttributeError: module 'ingest_helpers' has no attribute 'find_ingested_source'`.

- [ ] **Step 3: Implement `find_ingested_source()`**

At the top of `.forge/lib/ingest_helpers.py`, add `import frontmatter` to the imports (the imports become):

```python
import hashlib
import re
from pathlib import Path

import frontmatter
```

Then add this function after `scan_raw()`:

```python
def find_ingested_source(workspace_root=".", content_hash=None, source_path=None):
    """Find a previously-ingested source page in wiki/sources/.

    Searches every wiki/sources/*.md for a page whose frontmatter `content_hash`
    or `source_path` matches the argument given. Returns (slug, frontmatter_dict)
    for the first match, or None.

    `slug` is the page path inside wiki/ minus the .md suffix, e.g. "sources/foo".
    At least one of content_hash / source_path must be supplied.
    """
    if content_hash is None and source_path is None:
        raise ValueError("provide content_hash or source_path")
    wiki = Path(workspace_root) / "wiki"
    src_dir = wiki / "sources"
    if not src_dir.is_dir():
        return None
    for page in sorted(src_dir.rglob("*.md")):
        try:
            fm, _ = frontmatter.load(page)
        except frontmatter.FrontmatterError:
            continue
        if content_hash is not None and fm.get("content_hash") == content_hash:
            return str(page.relative_to(wiki).with_suffix("")), fm
        if source_path is not None and fm.get("source_path") == source_path:
            return str(page.relative_to(wiki).with_suffix("")), fm
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ingest_helpers.py -v`
Expected: PASS — all tests in the file (Tasks 2-4) pass.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/ingest_helpers.py tests/test_ingest_helpers.py
git commit -m "feat: add find_ingested_source() for content-hash dedup lookup"
```

---

### Task 5: Create `credentials.py` to load tool tokens

External tools (MinerU, Tavily) read their tokens from environment variables. WikiForge stores them in the gitignored `.forge/secrets/credentials.env`. `credentials.py` parses that file and injects keys into `os.environ`.

**Files:**
- Create: `.forge/lib/credentials.py`
- Test: `tests/test_credentials.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_credentials.py`:

```python
import os

import credentials


def test_parse_env_basic():
    assert credentials.parse_env("A=1\nB=two\n") == {"A": "1", "B": "two"}


def test_parse_env_ignores_comments_and_blanks():
    assert credentials.parse_env("# c\n\nA=1\n   # indented\nB=2\n") == {"A": "1", "B": "2"}


def test_parse_env_value_keeps_inner_equals():
    assert credentials.parse_env("K=a=b=c")["K"] == "a=b=c"


def test_parse_env_strips_whitespace():
    assert credentials.parse_env("  A = 1  \n") == {"A": "1"}


def test_load_credentials_missing_file(tmp_path):
    assert credentials.load_credentials(tmp_path / "nope.env") == {}


def test_load_credentials_into_environ(tmp_path, monkeypatch):
    f = tmp_path / "c.env"
    f.write_text("WF_TEST_TOKEN=xyz\n")
    monkeypatch.delenv("WF_TEST_TOKEN", raising=False)
    result = credentials.load_credentials(f, into_environ=True)
    assert result == {"WF_TEST_TOKEN": "xyz"}
    assert os.environ["WF_TEST_TOKEN"] == "xyz"


def test_load_credentials_real_env_wins(tmp_path, monkeypatch):
    f = tmp_path / "c.env"
    f.write_text("WF_TEST_TOKEN=fromfile\n")
    monkeypatch.setenv("WF_TEST_TOKEN", "fromenv")
    credentials.load_credentials(f, into_environ=True)
    assert os.environ["WF_TEST_TOKEN"] == "fromenv"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_credentials.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'credentials'`.

- [ ] **Step 3: Implement `credentials.py`**

Create `.forge/lib/credentials.py`:

```python
"""credentials.py — load local-only tool credentials into the environment.

Credentials live in `.forge/secrets/credentials.env` (gitignored, never
committed). The file holds `KEY=value` lines; blank lines and `#` comments are
ignored. ingest/explorer call `load_credentials()` before invoking external
tools (MinerU, Tavily) so those tools find their tokens in `os.environ`.

The file is optional: a workspace with no credentials still ingests, limited to
free-tier tooling (MinerU agent API; no Tavily web extraction).
"""
import os
from pathlib import Path

DEFAULT_PATH = ".forge/secrets/credentials.env"


def parse_env(text):
    """Parse `KEY=value` lines. Return a dict. Ignores blanks and `#` comments.

    The value keeps any `=` characters after the first one. Surrounding
    whitespace on key and value is stripped.
    """
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def load_credentials(path=DEFAULT_PATH, into_environ=True):
    """Read credentials from `path`. Return the parsed dict.

    A missing file yields {} — credentials are optional. When `into_environ` is
    True, each key is written to os.environ only if not already set, so a real
    environment variable always overrides the file (CI / shell overrides work).
    """
    p = Path(path)
    if not p.is_file():
        return {}
    creds = parse_env(p.read_text(encoding="utf-8"))
    if into_environ:
        for key, value in creds.items():
            os.environ.setdefault(key, value)
    return creds
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_credentials.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/credentials.py tests/test_credentials.py
git commit -m "feat: add credentials.py to load tool tokens from .forge/secrets"
```

---

### Task 6: Vendor the MinerU converter into the project

The `mineru-pdf-converter` skill is installed in the user's Claude Code scope and is not guaranteed present in every environment that runs a WikiForge curator. Vendor its converter script into `.forge/lib/` so ingest depends only on the project tree. The script is stdlib-only (`urllib`, `subprocess`+`curl`, `zipfile`), so vendoring is clean.

**Files:**
- Create: `.forge/lib/mineru_api.py`

- [ ] **Step 1: Copy the converter script into the project**

Run:

```bash
cp ~/.claude/skills/mineru-pdf-converter/mineru-api.py .forge/lib/mineru_api.py
```

(The destination uses an underscore — `mineru_api.py` — so it is also importable as a module name if ever needed. The source `mineru-api-token.json` is the user's personal token and is deliberately NOT vendored; the token comes from `MINERU_API_TOKEN` in `.forge/secrets/credentials.env`.)

- [ ] **Step 2: Verify the vendored script runs**

Run: `python3 .forge/lib/mineru_api.py --help`
Expected: prints the argparse usage (`usage: mineru_api.py [-h] [-o OUTPUT] ... file`), exits 0.

- [ ] **Step 3: Verify it has no third-party imports**

Run: `grep -E '^(import|from) ' .forge/lib/mineru_api.py`
Expected: only stdlib modules (`sys`, `time`, `os`, `json`, `argparse`, `shutil`, `subprocess`, `zipfile`, `tempfile`, `urllib.request`). No `requests` or other third-party package.

- [ ] **Step 4: Commit**

```bash
git add .forge/lib/mineru_api.py
git commit -m "feat: vendor the MinerU PDF/Office converter into .forge/lib"
```

---

### Task 7: Create `normalize.py` — dispatcher core and HTML conversion

`normalize.py` is the heart of the new ingest normalization layer. This task builds the dispatcher skeleton plus the offline HTML path; Tasks 8-9 add the MinerU and Tavily paths. Conversion output goes to a sibling `<stem>.converted/` directory; the original raw file is never touched.

**Files:**
- Create: `.forge/lib/normalize.py`
- Test: `tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_normalize.py`:

```python
import pytest

import normalize


def test_converted_dir_naming():
    d = normalize.converted_dir("raw/papers/foo.pdf")
    assert d.name == "foo.converted"
    assert str(d) == "raw/papers/foo.converted"


def test_plaintext_returns_original(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("# hi")
    assert normalize.normalize_source(note) == note


def test_directory_returns_itself(tmp_path):
    repo = tmp_path / "acme/widget@abc"
    repo.mkdir(parents=True)
    assert normalize.normalize_source(repo) == repo


def test_missing_source_raises(tmp_path):
    with pytest.raises(normalize.NormalizeError):
        normalize.normalize_source(tmp_path / "nope.pdf")


def test_unknown_extension_raises(tmp_path):
    weird = tmp_path / "thing.xyz"
    weird.write_text("data")
    with pytest.raises(normalize.NormalizeError, match="no normalizer"):
        normalize.normalize_source(weird)


def test_html_conversion(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>Title</h1><p>Body text here.</p>")
    out = normalize.normalize_source(page)
    assert out == tmp_path / "page.converted" / "page.md"
    text = out.read_text()
    assert "Title" in text and "Body text here." in text
    assert page.exists()  # original untouched


def test_html_conversion_idempotent(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>X</h1>")
    first = normalize.normalize_source(page)
    first.write_text("EDITED — should be reused, not regenerated")
    second = normalize.normalize_source(page)
    assert second == first
    assert second.read_text().startswith("EDITED")


def test_html_force_reconverts(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>X</h1>")
    first = normalize.normalize_source(page)
    first.write_text("STALE")
    second = normalize.normalize_source(page, force=True)
    assert "STALE" not in second.read_text()
    assert "X" in second.read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'normalize'`.

- [ ] **Step 3: Implement `normalize.py` (dispatcher + HTML path)**

Create `.forge/lib/normalize.py`:

```python
"""normalize.py — convert a raw source artifact into readable markdown.

The ingest skill processes one queued source at a time. Before drafting wiki
pages it normalizes the raw artifact: whatever format the source arrived in
(PDF, Office document, HTML, a saved URL), this module produces markdown.

Conversion output lands in a sibling `<stem>.converted/` directory next to the
original; the original raw file is never modified or removed. Plain markdown
notes and cloned repo directories need no conversion and are returned as-is.

Routing (see normalize_source):
  .pdf .docx .pptx .xls .xlsx   -> MinerU      (.forge/lib/mineru_api.py)
  .html .htm                    -> markdownify (offline, local)
  .url .weblink                 -> Tavily CLI  (`tvly extract`)
  .md .markdown .txt            -> none; the raw file is already readable
  a directory (cloned repo)     -> none; read its files directly
"""
import subprocess
import sys
from pathlib import Path

from credentials import load_credentials

MINERU_EXTS = {".pdf", ".docx", ".pptx", ".xls", ".xlsx"}
HTML_EXTS = {".html", ".htm"}
URL_EXTS = {".url", ".weblink"}
PLAINTEXT_EXTS = {".md", ".markdown", ".txt"}

_MINERU = Path(__file__).resolve().parent / "mineru_api.py"


class NormalizeError(Exception):
    """Conversion failed in a way the agent must escalate (request-human)."""


def converted_dir(raw_path):
    """Return the sibling output directory for a raw artifact.

    raw/papers/foo.pdf -> raw/papers/foo.converted
    """
    p = Path(raw_path)
    return p.parent / (p.stem + ".converted")


def _markdown_in(dir_path):
    """Return the first *.md file inside dir_path, or None."""
    if not Path(dir_path).is_dir():
        return None
    mds = sorted(Path(dir_path).glob("*.md"))
    return mds[0] if mds else None


def _convert_html(src, out_dir):
    try:
        from markdownify import markdownify
    except ImportError as e:
        raise NormalizeError(
            "markdownify is not installed; run: pip install -r requirements.txt"
        ) from e
    html = Path(src).read_text(encoding="utf-8", errors="replace")
    md = markdownify(html, heading_style="ATX")
    (out_dir / (Path(src).stem + ".md")).write_text(md, encoding="utf-8")


def normalize_source(raw_path, force=False):
    """Convert raw_path to markdown. Return the Path of the readable artifact.

    - plain markdown / text -> returns raw_path unchanged.
    - a directory (repo)    -> returns the directory unchanged.
    - a convertible file    -> returns <stem>.converted/<stem>.md.

    Idempotent: an existing non-empty .converted/ directory is reused unless
    `force` is True. Raises NormalizeError on any conversion failure.
    """
    p = Path(raw_path)
    if not p.exists():
        raise NormalizeError(f"source does not exist: {raw_path}")
    if p.is_dir():
        return p
    ext = p.suffix.lower()
    if ext in PLAINTEXT_EXTS:
        return p

    out_dir = converted_dir(p)
    existing = _markdown_in(out_dir)
    if existing is not None and not force:
        return existing

    load_credentials(into_environ=True)  # MINERU_API_TOKEN / TAVILY_API_KEY
    out_dir.mkdir(parents=True, exist_ok=True)

    if ext in MINERU_EXTS:
        _convert_mineru(p, out_dir)
    elif ext in HTML_EXTS:
        _convert_html(p, out_dir)
    elif ext in URL_EXTS:
        _convert_url(p, out_dir)
    else:
        raise NormalizeError(f"no normalizer for extension {ext!r}: {raw_path}")

    md = _markdown_in(out_dir)
    if md is None:
        raise NormalizeError(f"conversion produced no markdown for {raw_path}")
    return md
```

NOTE: `_convert_mineru` and `_convert_url` are referenced here but defined in Tasks 8 and 9. To keep this task's tests green, add temporary stubs at the end of the file now — Tasks 8 and 9 replace them:

```python
def _convert_mineru(src, out_dir):
    raise NormalizeError("MinerU path not yet implemented")  # replaced in Task 8


def _convert_url(src, out_dir):
    raise NormalizeError("Tavily path not yet implemented")  # replaced in Task 9
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: PASS — all 8 tests pass (none exercise the MinerU/Tavily stubs).

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/normalize.py tests/test_normalize.py
git commit -m "feat: add normalize.py dispatcher with HTML conversion path"
```

---

### Task 8: `normalize.py` — MinerU path for PDF and Office files

Replace the `_convert_mineru` stub with a real subprocess call to the vendored `mineru_api.py`. MinerU writes `<stem>.md` plus an `images/` subdirectory into the output directory. Tests mock `subprocess.run` so no network call is made.

**Files:**
- Modify: `.forge/lib/normalize.py`
- Test: `tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_normalize.py`:

```python
import subprocess


def test_pdf_routes_to_mineru(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "doc.md").write_text("# Converted by MinerU")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(pdf)
    assert out == tmp_path / "doc.converted" / "doc.md"
    assert out.read_text() == "# Converted by MinerU"
    assert any("mineru_api.py" in str(part) for part in calls[0])


def test_pdf_failure_raises_normalize_error(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF fake")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "File too large (12.0MB > 10MB).")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="MinerU"):
        normalize.normalize_source(pdf)


def test_docx_also_routes_to_mineru(tmp_path, monkeypatch):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK fake docx")

    def fake_run(cmd, **kwargs):
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.md").write_text("# Report")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(docx)
    assert out.read_text() == "# Report"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_normalize.py -k "pdf or docx" -v`
Expected: FAIL — `test_pdf_routes_to_mineru` and `test_docx_also_routes_to_mineru` raise `NormalizeError: MinerU path not yet implemented`.

- [ ] **Step 3: Replace the `_convert_mineru` stub**

In `.forge/lib/normalize.py`, replace this stub:

```python
def _convert_mineru(src, out_dir):
    raise NormalizeError("MinerU path not yet implemented")  # replaced in Task 8
```

with the real implementation:

```python
def _convert_mineru(src, out_dir):
    """Convert a PDF or Office file via the vendored MinerU CLI.

    MinerU writes <stem>.md (and an images/ subdir) into out_dir. Uses the free
    agent API unless MINERU_API_TOKEN is set, which load_credentials() will have
    placed in the environment for the subprocess to inherit.
    """
    cmd = [sys.executable, str(_MINERU), str(src), "-o", str(out_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise NormalizeError(
            f"MinerU conversion failed for {src} (exit {proc.returncode}). "
            f"For PDFs over the free-tier limit (10MB / 20 pages), set "
            f"MINERU_API_TOKEN in .forge/secrets/credentials.env. "
            f"stderr: {proc.stderr.strip()[-500:]}"
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: PASS — all tests pass (Task 7 tests still green, 3 new ones green).

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/normalize.py tests/test_normalize.py
git commit -m "feat: wire normalize.py PDF/Office conversion to vendored MinerU"
```

---

### Task 9: `normalize.py` — URL path via the Tavily CLI

Replace the `_convert_url` stub. A `.url` (or `.weblink`) file holds a single URL; `normalize.py` runs `tvly extract <url> -o <out>.md`. The Tavily CLI reads `TAVILY_API_KEY` from the environment (placed there by `load_credentials`). Tests mock `subprocess.run`.

**Files:**
- Modify: `.forge/lib/normalize.py`
- Test: `tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_normalize.py`:

```python
def test_url_routes_to_tvly(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com/article\n")

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "tvly" and cmd[1] == "extract"
        assert cmd[2] == "https://example.com/article"
        out = Path(cmd[cmd.index("-o") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# Extracted article")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(src)
    assert out == tmp_path / "article.converted" / "article.md"
    assert out.read_text() == "# Extracted article"


def test_url_failure_raises_normalize_error(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 3, "", "auth error")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="tvly"):
        normalize.normalize_source(src)


def test_url_empty_file_raises(tmp_path):
    src = tmp_path / "article.url"
    src.write_text("   \n")
    with pytest.raises(normalize.NormalizeError, match="no URL"):
        normalize.normalize_source(src)


def test_url_missing_cli_raises(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com\n")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("tvly")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="Tavily CLI"):
        normalize.normalize_source(src)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_normalize.py -k url -v`
Expected: FAIL — the `.url` tests raise `NormalizeError: Tavily path not yet implemented` (or, for `test_url_empty_file_raises`, the stub error rather than the "no URL" error).

- [ ] **Step 3: Replace the `_convert_url` stub**

In `.forge/lib/normalize.py`, replace this stub:

```python
def _convert_url(src, out_dir):
    raise NormalizeError("Tavily path not yet implemented")  # replaced in Task 9
```

with the real implementation:

```python
def _convert_url(src, out_dir):
    """Fetch a saved URL to markdown via the Tavily CLI (`tvly extract`).

    The .url/.weblink file holds the URL on its first non-blank line. tvly reads
    TAVILY_API_KEY from the environment (placed there by load_credentials()).
    """
    lines = [ln.strip() for ln in Path(src).read_text(encoding="utf-8").splitlines()]
    url = next((ln for ln in lines if ln), "")
    if not url:
        raise NormalizeError(f"{src} contains no URL")
    out_md = out_dir / (Path(src).stem + ".md")
    try:
        proc = subprocess.run(
            ["tvly", "extract", url, "-o", str(out_md)],
            capture_output=True, text=True,
        )
    except FileNotFoundError as e:
        raise NormalizeError(
            "the Tavily CLI (`tvly`) is not installed. Install it with "
            "`curl -fsSL https://cli.tavily.com/install.sh | bash` and set "
            "TAVILY_API_KEY in .forge/secrets/credentials.env."
        ) from e
    if proc.returncode != 0:
        raise NormalizeError(
            f"tvly extract failed for {url} (exit {proc.returncode}). "
            f"Check that TAVILY_API_KEY is set in .forge/secrets/credentials.env. "
            f"stderr: {proc.stderr.strip()[-300:]}"
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_normalize.py -v`
Expected: PASS — all normalize tests pass.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/normalize.py tests/test_normalize.py
git commit -m "feat: wire normalize.py URL conversion to the Tavily CLI"
```

---

### Task 10: Seed `credentials.env` from `bootstrap.py`

`bootstrap.py` creates the workspace skeleton. Add a function that seeds `.forge/secrets/credentials.env` with a commented template, so the new bootstrap Step 8 (Task 11) has a file to fill in.

**Files:**
- Modify: `.forge/lib/bootstrap.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bootstrap.py`:

```python
import bootstrap


def test_create_credentials_file(tmp_path):
    (tmp_path / ".forge/secrets").mkdir(parents=True)
    rel = bootstrap.create_credentials_file(tmp_path)
    assert rel == ".forge/secrets/credentials.env"
    content = (tmp_path / rel).read_text()
    assert "MINERU_API_TOKEN" in content
    assert "TAVILY_API_KEY" in content
    assert content.lstrip().startswith("#")  # template is fully commented


def test_create_credentials_file_idempotent(tmp_path):
    (tmp_path / ".forge/secrets").mkdir(parents=True)
    assert bootstrap.create_credentials_file(tmp_path) == ".forge/secrets/credentials.env"
    assert bootstrap.create_credentials_file(tmp_path) is None


def test_create_credentials_file_creates_missing_dir(tmp_path):
    # .forge/secrets/ does not exist yet — the function must create it
    rel = bootstrap.create_credentials_file(tmp_path)
    assert (tmp_path / rel).is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_bootstrap.py -v`
Expected: FAIL — `AttributeError: module 'bootstrap' has no attribute 'create_credentials_file'`.

- [ ] **Step 3: Add the credentials template and function to `bootstrap.py`**

In `.forge/lib/bootstrap.py`, add this constant and function after the `create_seed_files` function (after line 200):

```python
CREDENTIALS_TEMPLATE = """\
# .forge/secrets/credentials.env — local-only tool credentials (gitignored).
#
# Format: KEY=value, one per line. Loaded into the environment by
# .forge/lib/credentials.py before ingest/explorer invoke external tools.
# Blank lines and #-comments are ignored. A real environment variable of the
# same name always overrides the value here.
#
# Uncomment and fill the lines for the tools you use. Add new KEY=value lines
# for any other credentialed tool (audio transcription, OCR, ...) — the loader
# passes through every key it finds; no code change is needed.

# MinerU precision PDF/Office API (optional). Without a token, ingest uses the
# free agent API: 10MB / 20 pages per file. Token: https://mineru.net/
# MINERU_API_TOKEN=

# Tavily web extraction, used to fetch raw/web/*.url sources to markdown via the
# `tvly` CLI. Key: https://tavily.com/
# TAVILY_API_KEY=
"""


def create_credentials_file(workspace):
    """Seed .forge/secrets/credentials.env with the commented template.

    Returns the workspace-relative path string if the file was created, or None
    if it already existed (idempotent — never clobbers a filled-in file).
    """
    p = workspace / ".forge" / "secrets" / "credentials.env"
    if p.exists():
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(CREDENTIALS_TEMPLATE, encoding="utf-8")
    return str(p.relative_to(workspace))
```

- [ ] **Step 4: Call it from `main()` and report it**

In `.forge/lib/bootstrap.py`, in `main()`, after the line `symlinks_created = create_symlinks(workspace)`, add:

```python
    credentials_file = create_credentials_file(workspace)
```

Then add `credentials_file` to the `result` dict so it becomes:

```python
    result = {
        "domain": subs["{{domain}}"],
        "today": subs["{{today}}"],
        "substituted": substituted,
        "directories_created": directories_created,
        "seed_files_created": seed_files_created,
        "symlinks_created": symlinks_created,
        "credentials_file": credentials_file,
    }
```

Also update the module docstring's numbered list: after item `3.` (creates empty directories) the docstring mentions `.forge/secrets/`; append a new item:

```
  5. Seeds `.forge/secrets/credentials.env` with a commented template for
     tool credentials (MinerU, Tavily, and any future tools).
```

(Renumber the existing symlink item from `4.` to `6.`, or simply insert as item `5.` if the symlink item is `4.` — keep the list sequential.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_bootstrap.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 6: Commit**

```bash
git add .forge/lib/bootstrap.py tests/test_bootstrap.py
git commit -m "feat: seed .forge/secrets/credentials.env during bootstrap"
```

---

### Task 11: Add the credentials step to the bootstrap runbook

Add a new **Step 8 — Configure tool credentials (optional)** to `bootstrap.md`, between the notifications step (Step 7) and the lint-verification step. Renumber the three following steps. The five-question interview budget is untouched — this is a separate optional configuration step, exactly like Step 7 (notifications), and is not a contract invariant.

**Files:**
- Modify: `bootstrap.md`

- [ ] **Step 1: Fix the prerequisites cross-reference**

In `bootstrap.md`, the Prerequisites section says "Step 9 handles both". Find:

```
- You are on a clean working tree (a fresh clone). You may be on `master` or on a branch you created for this run — Step 9 handles both.
```

Replace `Step 9` with `Step 10`:

```
- You are on a clean working tree (a fresh clone). You may be on `master` or on a branch you created for this run — Step 10 handles both.
```

- [ ] **Step 2: Insert the new Step 8**

In `bootstrap.md`, find the end of Step 7 (the line with its log marker) and the start of the current Step 8:

```
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-7 complete (channels: <list-or-none>)" >> .forge/bootstrap.log
```

```
### Step 8 — Verify the empty workspace
```

Insert the entire new Step 8 between them (after the closing ``` of Step 7's log marker, before `### Step 8 — Verify the empty workspace`):

````
### Step 8 — Configure tool credentials (optional)

ingest and explorer call external tools to turn raw sources into markdown:
MinerU (PDF / Office → markdown) and the Tavily CLI (web URL → markdown). Both
have free tiers; API tokens unlock higher limits. Credentials live in
`.forge/secrets/credentials.env` — gitignored, local-only, never committed.
Step 3 seeded that file with a commented template.

Ask the human:

"Configure tool credentials now? (y/n, default n — you can edit
`.forge/secrets/credentials.env` by hand anytime later.)"

- **No / skip** → leave the seeded template as-is (all keys commented out;
  ingest falls back to free-tier tooling). Proceed.
- **Yes** → walk the human through each credential, one at a time. For each
  value the human provides, uncomment-and-fill the matching line in
  `.forge/secrets/credentials.env` (or append a new `KEY=value` line). Print
  the key *name* back for confirmation — never the value.

  1. **MinerU API token** — "Paste your MinerU API token (unlocks 200MB / 200
     pages per file), or press enter to skip (free tier: 10MB / 20 pages)."
     On a value, set `MINERU_API_TOKEN=<value>`.
  2. **Tavily API key** — "Paste your Tavily API key (`tvly-...`, used to fetch
     web sources), or press enter to skip." On a value, set
     `TAVILY_API_KEY=<value>`.
  3. **Additional credentials** — "Any other tool credentials to add now
     (audio transcription, OCR, ...)? Enter as `KEY=value`, or blank to
     finish." Loop, appending each line, until the human enters a blank line.

Credentials are optional and **not** a contract invariant — like notifications
(Step 7), this step exists so the human is not surprised later, and changes
nothing if skipped. The file is freely re-editable after bootstrap.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-8 complete (credentials: <key-names-or-none>)" >> .forge/bootstrap.log
```

````

- [ ] **Step 3: Renumber the verification step (old Step 8 → Step 9)**

Find:

```
### Step 8 — Verify the empty workspace
```

Replace with:

```
### Step 9 — Verify the empty workspace
```

In that step's body, find:

```
If lint fails: stop. Either the templates have a bug, the substitution produced invalid frontmatter, or the linter has a regression. Report which page failed which check. Do not proceed to Step 9 — a failed lint here means the workspace cannot be trusted as a clean foundation.
```

Replace `Do not proceed to Step 9` with `Do not proceed to Step 10`.

Then find that step's log marker:

```
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-8 complete (lint: 0/0)" >> .forge/bootstrap.log
```

Replace `step-8 complete` with `step-9 complete`.

- [ ] **Step 4: Renumber the finalize step (old Step 9 → Step 10)**

Find:

```
### Step 9 — Branch, finalize, commit
```

Replace with:

```
### Step 10 — Branch, finalize, commit
```

- [ ] **Step 5: Renumber the brief step (old Step 10 → Step 11) and mention credentials**

Find:

```
### Step 10 — Brief the human
```

Replace with:

```
### Step 11 — Brief the human
```

In the printed message block of that step, find:

```
Ongoing reference: README.md (overview), CLAUDE.md/AGENTS.md/GEMINI.md (skills),
schema.md (page-type spec).
```

Replace with:

```
Tool credentials: edit .forge/secrets/credentials.env to add MinerU / Tavily
API keys (or any other tool tokens) — ingest works without them on free tiers.

Ongoing reference: README.md (overview), CLAUDE.md/AGENTS.md/GEMINI.md (skills),
schema.md (page-type spec).
```

- [ ] **Step 6: Verify the renumbering is consistent**

Run: `grep -n '^### Step ' bootstrap.md`
Expected: a clean sequence — `Step 1` through `Step 11`, with `Step 8 — Configure tool credentials (optional)` present and no duplicate or skipped numbers.

Run: `grep -n 'step-[0-9]* complete' bootstrap.md`
Expected: log markers `step-2` through `step-10` each appear once, with `step-8 complete (credentials:` present.

- [ ] **Step 7: Commit**

```bash
git add bootstrap.md
git commit -m "feat: add optional tool-credentials step to the bootstrap runbook"
```

---

### Task 12: Rewrite the ingest SKILL.md

Update `.forge/skills/ingest/SKILL.md` to (a) fix the `log.md` path inconsistency, (b) reference `scan_raw` for `--scan`, (c) add the normalization step with the MinerU/Tavily/markdownify routing and credential handling, and (d) add a per-type frontmatter cheatsheet so pages pass lint on the first attempt.

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md`

- [ ] **Step 1: Fix the log-path inconsistency in step 1**

In `.forge/skills/ingest/SKILL.md`, find (in "### 1. Check for prior ingestion"):

```
- **Same hash → skip.** Append a one-line log entry to `.forge/log.md` and move on.
```

Replace with:

```
- **Same hash → skip.** Append a one-line log entry to `wiki/log.md` and move on.
```

(`wiki/log.md` is the wiki operation log — consistent with step 6. `.forge/log.md` is reserved for curator-side items needing human attention, e.g. flagged contradictions in step 8. `find_ingested_source` from `ingest_helpers` does this lookup — see step 1's note below.)

- [ ] **Step 2: Reference `scan_raw` and `find_ingested_source` for the helpers**

Find the `--scan` mode bullet:

```
- **`ingest --scan`** — walk `raw/`, find files not already in `.forge/queue.md` or `wiki/sources/`, append them as `[ ]` entries, then process pending entries.
```

Replace with:

```
- **`ingest --scan`** — walk `raw/` with `ingest_helpers.scan_raw()`, find sources not already in `.forge/queue.md` or `wiki/sources/`, append them as `[ ]` entries with `ingest_helpers.append_queue_entry()`, then process pending entries.
```

Then, in "### 1. Check for prior ingestion", find:

```
Look in `wiki/sources/` for any page whose frontmatter `content_hash:` equals `h`.
```

Replace with:

```
Use `ingest_helpers.find_ingested_source(content_hash=h)` to look for an existing `wiki/sources/` page with that hash (it also accepts `source_path=` to match by raw path):

```python
from ingest_helpers import find_ingested_source
hit = find_ingested_source(content_hash=h)   # -> (slug, frontmatter) or None
```
```

- [ ] **Step 3: Replace step 3 with the normalization-then-read step**

Find the entire "### 3. Read the source" section:

```
### 3. Read the source

- **Papers (PDF):** read directly via your Read tool. If you can't extract text, write a request to `.forge/requests/inbox/` with `type: pdf-text-extraction` and `urgency: blocking`. Don't attempt to draft a page from an unreadable source.
- **Repos:** start with `README` and any top-level config files. Use `ingest_helpers.enumerate_repo_files(repo_root)` for an ordered list of "interesting" files. Read selectively — not the whole repo.
- **Docs / web:** read directly. They should already be plain markdown if extracted properly.
- **Notes:** read directly.
```

Replace it entirely with:

````
### 3. Normalize the source to markdown

Raw sources arrive in many formats. Before reading, convert the artifact to
markdown with the normalizer. It routes by file type and writes output to a
sibling `<stem>.converted/` directory — the original raw file is left in place,
untouched.

```python
from normalize import normalize_source, NormalizeError
try:
    readable = normalize_source("raw/papers/foo.pdf")   # -> Path to markdown
except NormalizeError as e:
    ...   # see "If normalization fails" below
```

| Raw type (location)                  | Tool the normalizer uses          |
| ------------------------------------ | --------------------------------- |
| `raw/papers/*.pdf`                    | MinerU (PDF → markdown + images)  |
| `raw/docs/*.{pdf,docx,pptx,xls,xlsx}` | MinerU                            |
| `raw/web/*.{html,htm}`                | markdownify (offline, local)      |
| `raw/web/*.url` (file holding a URL)  | Tavily CLI (`tvly extract`)       |
| `raw/notes/*.{md,txt}`                | none — already readable, returned as-is |
| `raw/repos/<org>/<repo>@<sha>/`       | none — a directory, returned as-is |

MinerU uses the free agent API (10MB / 20 pages per file) unless
`MINERU_API_TOKEN` is set in `.forge/secrets/credentials.env`, which unlocks the
precision API (200MB / 200 pages). The Tavily path needs `TAVILY_API_KEY` in the
same file. `normalize_source` loads `.forge/secrets/credentials.env`
automatically — you do not load it yourself.

**If normalization fails** (`NormalizeError`) — e.g. a PDF over the free-tier
limit with no token, or the Tavily CLI not installed — do NOT draft a page from
an unreadable source. Set the queue entry to `[!]` blocked
(`ingest_helpers.set_queue_state(queue_path, source_path, "!", note="req <id>")`)
and write a request via the request-human skill (`type: large-download` for an
oversize PDF, `type: paid-api` or `human-judgement` otherwise).

### 4. Read the source

- **Papers / docs:** read the converted markdown that `normalize_source`
  returned. Figures are in the sibling `images/` directory if you need them.
- **Repos:** start with `README` and any top-level config files. Use
  `ingest_helpers.enumerate_repo_files(repo_root)` for an ordered list of
  "interesting" files. Read selectively — not the whole repo.
- **Web:** read the converted markdown.
- **Notes:** `normalize_source` returns the note path unchanged — read it
  directly.
````

NOTE: the original steps numbered 4-8 ("Gather context", "Draft pages", "Update meta files", "Update the queue", "Surface follow-ups") must each be renumbered +1, becoming steps 5-9, because a new step 4 ("Read the source") now exists. Find each heading `### 4. Gather context`, `### 5. Draft pages`, `### 6. Update meta files`, `### 7. Update the queue`, `### 8. Surface follow-ups` and rewrite them as `### 5. Gather context`, `### 6. Draft pages`, `### 7. Update meta files`, `### 8. Update the queue`, `### 9. Surface follow-ups` respectively. Do not change their bodies.

- [ ] **Step 4: Add the frontmatter cheatsheet section**

Find the section heading:

```
## Lint before you stop
```

Insert this entire new section immediately before it:

````
## Frontmatter cheatsheet

Encode this so pages pass lint on the first try. The full spec is `schema.md`;
this is the compressed version ingest needs in hand.

**Every page** requires: `title`, `type`, `created` (YYYY-MM-DD),
`last_verified` (YYYY-MM-DD), `confidence`
(`verified` | `likely` | `low` | `placeholder` | `refuted`).

Per-type extra required fields and the edge types each type may declare in
frontmatter:

| Type           | Extra required fields                                                    | Frontmatter edges allowed              |
| -------------- | ------------------------------------------------------------------------ | -------------------------------------- |
| `concept`      | —                                                                        | none                                   |
| `convention`   | —                                                                        | none                                   |
| `code-pattern` | `repo`, `commit` (40-char sha), `path`, `lines`, `language`               | `supersedes`, `implements`             |
| `claim`        | `status` (`validated`\|`likely`\|`open`\|`refuted`), `evidence`, `counter_evidence` | `extends`, `contradicts`, `supersedes` |
| `source`       | `source_type` (`paper`\|`repo`\|`doc`\|`web`\|`note`), `source_path`, `content_hash` | none                          |
| `entity`       | `entity_type` (`person`\|`lab`\|`project`\|`tool`\|`organization`)        | none                                   |

Rules the linter enforces — get these right up front:

- A `claim` with **both** `evidence:` and `counter_evidence:` empty is a hard
  error. At least one must be non-empty.
- Declaring an edge type not in the "allowed" column is a `disallowed-edge-type`
  error. When unsure, prefer a plain prose `[[wikilink]]` (always allowed, emits
  a `references` edge).
- A `code-pattern`'s `repo` / `commit` / `path` must resolve to a real file at
  `raw/repos/<org>/<repo>@<commit>/<path>`, or lint reports `excerpt-missing`.
- Slugs are unique across **all** types — `concepts/foo` and `claims/foo`
  collide (`duplicate-slug` error).
- `confidence` is honest: a single source supports `likely` at best; unverified
  synthesis is `low`; a stub pending more reading is `placeholder`.
````

- [ ] **Step 5: Add normalize/credentials to the "See also" list**

Find the "## See also" section and its existing bullets. After the `schema.md` bullet, add:

```
- `.forge/lib/normalize.py` — how raw artifacts of each type become markdown
- `.forge/lib/credentials.py` — how tool tokens are loaded from `.forge/secrets/`
```

- [ ] **Step 6: Verify the document is internally consistent**

Run: `grep -n '^### [0-9]' .forge/skills/ingest/SKILL.md`
Expected: steps `1` through `9` in order, with `3. Normalize the source to markdown` and `4. Read the source` present, no duplicate numbers.

Run: `grep -n 'log.md' .forge/skills/ingest/SKILL.md`
Expected: ingest-activity references point to `wiki/log.md`; only contradiction-flagging (step 9) points to `.forge/log.md`.

- [ ] **Step 7: Commit**

```bash
git add .forge/skills/ingest/SKILL.md
git commit -m "docs: rewrite ingest SKILL.md with normalization step and frontmatter cheatsheet"
```

---

### Task 13: Full verification and Phase 5 integration runbook

Run the whole automated suite to confirm no regressions, then write the manual integration runbook that PLAN_Init.md's Phase 5 test calls for (a real ingest of a PDF and a repo can only be exercised against a bootstrapped domain workspace, not this framework repo).

**Files:**
- Create: `tests/INTEGRATION_ingest.md`

- [ ] **Step 1: Run the entire automated test suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — every test from Tasks 2-10 passes; 0 failures.

- [ ] **Step 2: Smoke-test the normalizer end-to-end on a local HTML file**

Run:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, ".forge/lib")
import tempfile, pathlib
from normalize import normalize_source
d = pathlib.Path(tempfile.mkdtemp())
p = d / "demo.html"
p.write_text("<h1>Demo</h1><p>Hello WikiForge.</p>")
out = normalize_source(p)
print("converted ->", out)
print(out.read_text())
assert "Demo" in out.read_text() and "Hello WikiForge." in out.read_text()
assert out == d / "demo.converted" / "demo.md"
print("OK")
EOF
```

Expected: prints the converted path and markdown, ends with `OK`, exits 0.

- [ ] **Step 3: Verify `mineru_api.py` and `bootstrap.py` still import cleanly**

Run: `python3 -c "import sys; sys.path.insert(0,'.forge/lib'); import normalize, credentials, ingest_helpers, bootstrap; print('imports OK')"`
Expected: prints `imports OK`, exits 0.

- [ ] **Step 4: Write the integration runbook**

Create `tests/INTEGRATION_ingest.md`:

```markdown
# Integration test — ingest (PLAN_Init.md Phase 5)

This is the manual test PLAN_Init.md Phase 5 specifies. It cannot run as a unit
test: it needs a bootstrapped domain workspace, network access, and a real
agent invoking the ingest skill. Run it after any change to ingest, normalize,
or the ingest helpers.

## Setup

1. From a fresh clone, run the bootstrap workflow (`bootstrap.md`) to produce an
   initialized workspace. During Step 8, optionally enter a `MINERU_API_TOKEN`.
2. Confirm `.forge/secrets/credentials.env` exists and `.forge/queue.md`,
   `wiki/index.md`, `wiki/log.md` were seeded.

## Test A — ingest a PDF paper

1. Place one arXiv PDF (< 20 pages if no MinerU token) in `raw/papers/`.
2. Invoke the ingest skill: `ingest raw/papers/<file>.pdf`.
3. Verify:
   - `raw/papers/<file>.converted/<file>.md` was created; the original PDF is
     still present and unmodified.
   - `wiki/sources/<slug>.md` exists with valid frontmatter: `content_hash`
     matches `ingest_helpers.content_hash`, `source_type: paper`, `source_path`
     points at the PDF.
   - `wiki/index.md` has a new entry; `wiki/log.md` has an `ingest` line.
   - `python3 .forge/lib/lint.py --report` reports 0 errors.
4. Re-run `ingest` on the same PDF — it must skip (same content hash) and log
   the skip, creating no duplicate page.

## Test B — ingest a repo

1. Clone a small public GitHub repo into
   `raw/repos/<org>/<repo>@<full-sha>/`.
2. Invoke `ingest raw/repos/<org>/<repo>@<sha>`.
3. Verify:
   - A `wiki/sources/<slug>.md` page exists.
   - Any `wiki/code-patterns/<slug>.md` pages carry full provenance
     (`repo`, `commit`, `path`, `lines`, `language`) and the cited file
     resolves under `raw/repos/`.
   - `python3 .forge/lib/lint.py --report` reports 0 errors.

## Test C — ingest a web URL

1. Write a file `raw/web/<name>.url` containing one public URL.
2. Ensure `TAVILY_API_KEY` is set in `.forge/secrets/credentials.env`.
3. Invoke `ingest raw/web/<name>.url`.
4. Verify `raw/web/<name>.converted/<name>.md` was created and a
   `wiki/sources/` page drafted.

## Pass criteria

All three tests produce lint-clean pages with no manual frontmatter fixes, and
the re-run in Test A correctly deduplicates.
```

- [ ] **Step 5: Commit**

```bash
git add tests/INTEGRATION_ingest.md
git commit -m "test: add Phase 5 ingest integration runbook"
```

---

## Self-review notes

- **Spec coverage** — the seven audited ingest gaps map to: Task 3 (`--scan` helper), Task 4 (dedup lookup), Task 2 (crash-safe queue), Task 12 step 1 (`log.md` inconsistency), Task 12 step 4 (schema cheatsheet), Task 13 (Phase 5 exercise), Tasks 6-9 (PDF/format normalization). The user's additional asks map to: Tasks 6-9 (MinerU blended into ingest, plus the other source-type tools — see the reference table), Tasks 10-11 (bootstrap credentials stage with an extensible slot), Task 5 (credential loading).
- **Out of scope (deliberate)** — explorer-side use of these credentials; private-repo `GITHUB_TOKEN` (user did not select it; v1 is public repos only); multimodal image handling (MinerU emits `images/` but ingest does not yet build pages from them — consistent with PLAN_Init.md's v1 exclusions).
- **Design constraints honored** — all new code is curator-side Python (`.forge/lib/`), never bundle-side; the bundle's POSIX-only `bin/wiki-*` scripts are untouched. The five-question bootstrap interview budget is unchanged; the new Step 8 is an optional configuration step like Step 7, not an interview question, and adds no contract invariant.
```
