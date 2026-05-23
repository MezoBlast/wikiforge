"""credentials.py — load local-only tool credentials into the environment.

Credentials live in `.forge/secrets/credentials.env` (gitignored, never
committed). The file holds `KEY=value` lines; blank lines and `#` comments are
ignored. ingest/explorer call `load_credentials()` before invoking external
tools (MinerU, Tavily) so those tools find their tokens in `os.environ`.

The file is optional: a workspace with no credentials still ingests, limited to
free-tier tooling (MinerU agent API; no Tavily web extraction).
"""
import os
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / ".forge" / "secrets" / "credentials.env"


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


def set_credential(key, value, *, path=None):
    """Write `KEY=value` to credentials.env, in place.

    - If a line matching `^\\s*#?\\s*<KEY>\\s*=` exists, replace it (so a
      previously commented or set key is uncommented and updated).
    - Otherwise append `<KEY>=<value>\\n` to the end of the file.
    - All other lines are preserved unchanged.
    - An empty or whitespace-only `value` raises ValueError — an uncommented
      empty key is worse than the commented default (it suppresses the
      environment-variable override that `load_credentials` honors).
    - `path` defaults to DEFAULT_PATH. A missing file is created with mode
      0o600; an existing file's mode is not changed.
    """
    if not value or not value.strip():
        raise ValueError(f"refusing to write empty value for {key}")
    if "\n" in value or "\r" in value:
        raise ValueError(f"refusing to write multi-line value for {key}")
    target = Path(path) if path is not None else DEFAULT_PATH
    new_line = f"{key}={value}\n"
    pattern = re.compile(r"^\s*#?\s*" + re.escape(key) + r"\s*=")
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if pattern.match(ln):
                lines[i] = new_line
                break
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(new_line)
        target.write_text("".join(lines), encoding="utf-8")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_line, encoding="utf-8")
        os.chmod(target, 0o600)
