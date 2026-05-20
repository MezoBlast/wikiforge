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
