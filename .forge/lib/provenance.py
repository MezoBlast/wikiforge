"""provenance.py — extract code excerpts from raw/repos/ for code-pattern pages.

Each `code-pattern` page declares `(repo, commit, path, lines)` in its frontmatter.
At build time, this module reads the file at `raw/repos/<repo>@<commit>/<path>`,
extracts the cited line ranges, and returns the excerpt with a provenance header
prepended. The build copies the result to `wiki/snippets/<basename>.txt`.

Line ranges:
  "10"            — single line
  "10-45"         — inclusive range
  "10-45,60-72"   — multiple ranges, separated by `# --- gap ---`
"""
from pathlib import Path


class ProvenanceError(Exception):
    pass


def parse_lines(spec):
    """Parse a line-spec string into a list of (start, end) inclusive tuples."""
    if isinstance(spec, int):
        return [(spec, spec)]
    spec = str(spec).strip()
    if not spec:
        raise ProvenanceError("empty line spec")
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a_s, b_s = part.split("-", 1)
                a, b = int(a_s.strip()), int(b_s.strip())
            else:
                a = b = int(part)
        except ValueError:
            raise ProvenanceError(f"invalid line spec component: {part!r}")
        if a < 1 or b < a:
            raise ProvenanceError(f"invalid range {a}-{b}")
        out.append((a, b))
    if not out:
        raise ProvenanceError(f"no ranges parsed from: {spec!r}")
    return out


def extract(raw_dir, repo, commit, path, lines):
    """Return excerpt text (with provenance header). Raises ProvenanceError on failure."""
    src = Path(raw_dir) / "repos" / f"{repo}@{commit}" / path
    if not src.exists():
        raise ProvenanceError(f"source not found: {src}")
    if not src.is_file():
        raise ProvenanceError(f"source is not a file: {src}")
    with open(src, "r", encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()
    ranges = parse_lines(lines)
    chunks = []
    for start, end in ranges:
        if end > len(all_lines):
            raise ProvenanceError(
                f"line range {start}-{end} out of bounds "
                f"(file has {len(all_lines)} lines): {src}"
            )
        chunks.append("".join(all_lines[start - 1 : end]).rstrip())
    excerpt = "\n\n# --- gap ---\n\n".join(chunks)
    header = (
        f"# Provenance: {repo}@{commit}\n"
        f"# Path:       {path}\n"
        f"# Lines:      {lines}\n"
        f"#\n"
        f"# Extracted by wikiforge build at the pinned commit. Even if upstream\n"
        f"# moves on, this excerpt remains the canonical truth for the cited page.\n"
        f"\n"
    )
    return header + excerpt + "\n"
