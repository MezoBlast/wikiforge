"""ingest_helpers.py — utilities the ingest skill calls.

The ingest skill itself is a workflow (see .forge/skills/ingest/SKILL.md). These
helpers handle the mechanical parts: hashing, source-type detection, repo file
enumeration, and a queue API for the append-only `.forge/queue.md`.

Heavy PDF / repo parsing is intentionally NOT done here — the curator agent has
its own Read tool and can inspect files directly. These helpers exist where
mechanical correctness matters (dedup hashes, queue state machine).
"""
import hashlib
import re
from pathlib import Path

import frontmatter

QUEUE_STATES = {" ", "~", "x", "!"}  # pending, in-progress, done, blocked
# path is non-greedy so source paths containing spaces are captured whole;
# the optional ` | <note>` suffix still separates correctly.
QUEUE_ENTRY_RE = re.compile(r"^- \[(?P<state>.)\]\s+(?P<path>.+?)(?:\s*\|\s*(?P<note>.*))?$")

QUEUE_HEADER = (
    "# .forge/queue.md — append-only ingest queue\n"
    "<!-- See schema.md or .forge/skills/ingest/SKILL.md for entry format. -->\n"
    "<!-- States: [ ] pending  [~] in progress  [x] done  [!] blocked. -->\n"
)


def content_hash(path, length=16):
    """Return 'sha256:<first-length-hex-chars>' for the file at path."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:length]}"


def detect_source_type(path):
    """Classify a path in raw/ into one of {paper, repo, doc, web, note} or None."""
    p = Path(path)
    parts = p.parts
    if "papers" in parts:
        return "paper"
    if "repos" in parts:
        return "repo"
    if "docs" in parts:
        return "doc"
    if "web" in parts:
        return "web"
    if "notes" in parts:
        return "note"
    # fall back to suffix
    if p.suffix.lower() == ".pdf":
        return "paper"
    if p.is_dir():
        return "repo" if (p / ".git").exists() else None
    return None


def enumerate_repo_files(repo_root, max_files=200):
    """Yield interesting files in a `raw/repos/<org>/<name>@<sha>/` directory.

    Prioritization (in order):
      1. README, LICENSE, CONTRIBUTING (case-insensitive, any extension)
      2. Top-level config: setup.py, pyproject.toml, package.json, Cargo.toml, go.mod
      3. Source files under src/, lib/, the package directory matching <name>
      4. Tests (de-prioritized; included only if budget remains)

    Stops after `max_files`. Caller decides which to actually read.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return []
    canonical_basenames = {"readme", "license", "contributing", "changelog"}
    canonical_configs = {
        "setup.py", "setup.cfg", "pyproject.toml", "package.json",
        "cargo.toml", "go.mod", "build.gradle", "pom.xml", "makefile",
    }
    head, rest, tests = [], [], []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if any(part in {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
               for part in f.parts):
            continue
        bn = f.name.lower()
        stem = f.stem.lower()
        rel = f.relative_to(root)
        if stem in canonical_basenames or bn in canonical_configs:
            head.append(rel)
        elif "test" in rel.parts or stem.startswith("test_"):
            tests.append(rel)
        else:
            rest.append(rel)
        if len(head) + len(rest) + len(tests) >= max_files * 3:
            break
    combined = (head + rest)[: max(0, max_files - 5)] + tests[:5]
    return combined[:max_files]


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


def append_queue_entry(queue_path, source_path, note=""):
    """Append a `[ ] <path> | <note>` line if not already present.

    Creates the queue file (with its standard header) if it does not exist.
    """
    p = Path(queue_path)
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(QUEUE_HEADER, encoding="utf-8")
    text = p.read_text(encoding="utf-8")
    for _, _, existing, _ in parse_queue(p):
        if existing == source_path:
            return False
    line = f"- [ ] {source_path}"
    if note:
        line += f" | {note}"
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text + line + "\n", encoding="utf-8")
    return True


def set_queue_state(queue_path, source_path, new_state, note=None):
    """Mutate an existing entry's state marker. new_state in QUEUE_STATES."""
    if new_state not in QUEUE_STATES:
        raise ValueError(f"invalid state {new_state!r}; must be one of {sorted(QUEUE_STATES)}")
    p = Path(queue_path)
    if not p.is_file():
        raise FileNotFoundError(f"queue file does not exist: {queue_path}")
    text = p.read_text(encoding="utf-8")
    out = []
    found = False
    for line in text.splitlines():
        m = QUEUE_ENTRY_RE.match(line.rstrip())
        if m and m.group("path") == source_path:
            n = note if note is not None else m.group("note") or ""
            new = f"- [{new_state}] {source_path}"
            if n:
                new += f" | {n}"
            out.append(new)
            found = True
        else:
            out.append(line)
    if not found:
        raise KeyError(f"queue entry not found for {source_path}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def slugify(text):
    """Turn an arbitrary string into a wiki slug: lowercase, ASCII hyphens, no edges."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
