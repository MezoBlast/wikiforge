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

QUEUE_STATES = {" ", "~", "x", "!"}  # pending, in-progress, done, blocked
QUEUE_ENTRY_RE = re.compile(r"^- \[(?P<state>.)\]\s+(?P<path>\S+)(?:\s*\|\s*(?P<note>.*))?$")


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


def parse_queue(queue_path):
    """Yield (line_number, state, source_path, note) for each entry in queue.md."""
    text = Path(queue_path).read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        m = QUEUE_ENTRY_RE.match(line.rstrip())
        if m:
            yield i, m.group("state"), m.group("path"), (m.group("note") or "").strip()


def append_queue_entry(queue_path, source_path, note=""):
    """Append a `[ ] <path> | <note>` line if not already present."""
    p = Path(queue_path)
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
