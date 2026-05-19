"""wikilinks.py — extract [[wikilinks]] from prose and typed relationships from frontmatter.

Used by both `lint.py` (validation) and `build.sh` (constructing links.tsv).

Edge types are validated against the v1 vocabulary (schema_spec.EDGE_TYPES).
Unknown edge types are a build-blocking error; lint surfaces them as `unknown-edge-type`.
"""
import re

import schema_spec as S

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def extract_prose_links(body):
    """Yield raw wikilink targets in `body`, ignoring HTML comments."""
    text = _HTML_COMMENT_RE.sub("", body or "")
    for m in _WIKILINK_RE.finditer(text):
        yield m.group(1).strip()


def extract_frontmatter_edges(fm):
    """Yield (edge_type, target_slug) for each typed relationship in `fm`."""
    if not isinstance(fm, dict):
        return
    for edge in S.TYPED_EDGE_FIELDS:
        vals = fm.get(edge)
        if not vals:
            continue
        if not isinstance(vals, list):
            vals = [vals]
        for v in vals:
            if isinstance(v, str):
                yield edge, v.strip()


def normalize_target(target):
    """Strip an optional #anchor; return the slug portion."""
    return target.split("#", 1)[0].strip()


def resolve(target, valid_slugs, basename_index):
    """Resolve a target string to a canonical slug, or None if not found / ambiguous.

    Resolution order:
      1. Exact match against valid_slugs.
      2. Basename shorthand: if `target` matches exactly one slug's basename.
    """
    if target in valid_slugs:
        return target
    matches = basename_index.get(target, ())
    if len(matches) == 1:
        return matches[0]
    return None  # missing or ambiguous (caller can inspect basename_index for diagnostics)
