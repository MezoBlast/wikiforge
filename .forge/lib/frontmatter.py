"""frontmatter.py — parse, validate, dump YAML frontmatter from markdown files."""
import re
from pathlib import Path

import yaml

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


class FrontmatterError(Exception):
    pass


def split(text):
    """Return (frontmatter_dict, body_str). Raises if no frontmatter block."""
    m = _FM_RE.match(text)
    if not m:
        raise FrontmatterError("no frontmatter block (file must start with --- block)")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"YAML parse error: {e}")
    if not isinstance(fm, dict):
        raise FrontmatterError(
            f"frontmatter is not a mapping (got {type(fm).__name__})"
        )
    body = text[m.end():]
    return fm, body


def load(path):
    """Read path and return (frontmatter, body)."""
    return split(Path(path).read_text(encoding="utf-8"))


def dump(fm, body):
    """Render fm + body back to text. Preserves frontmatter key order."""
    yaml_text = yaml.safe_dump(
        fm, default_flow_style=False, sort_keys=False, allow_unicode=True
    ).rstrip()
    return f"---\n{yaml_text}\n---\n{body}"
