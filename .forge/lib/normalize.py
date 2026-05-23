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

_AGENT_OFFICEX_EXTS = {".docx", ".pptx", ".xlsx"}
_MINERU_FREE_TIER_MB = 10

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


def agent_extract_advice(raw_path):
    """Whether raw_path is a candidate for an agent self-extract fallback.

    Returns (eligible, mechanism, reason).
    - mechanism is one of 'pdf-read', 'unzip-officex', 'html-text', 'none'.
    - reason is a diagnostic string for the warning prompt and the headless
      log line; it is NOT load-bearing for control flow.
    """
    p = Path(raw_path)
    ext = p.suffix.lower()
    try:
        creds = load_credentials(into_environ=False)
    except Exception:
        # Any failure (missing file, unreadable file, parse error) is treated
        # as "no credentials"; reason is best-effort and not load-bearing.
        creds = {}
    token_present = bool(creds.get("MINERU_API_TOKEN", "").strip())
    size_mb = None
    if p.exists() and p.is_file():
        size_mb = p.stat().st_size / (1024 * 1024)

    if ext == ".pdf":
        return True, "pdf-read", _mineru_reason(size_mb, token_present)
    if ext in _AGENT_OFFICEX_EXTS:
        return True, "unzip-officex", _mineru_reason(size_mb, token_present)
    if ext in HTML_EXTS:
        return True, "html-text", "markdownify conversion failed (offline converter)"
    if ext == ".xls":
        return False, "none", "legacy OLE binary, not self-extractable"
    if ext in URL_EXTS:
        return False, "none", "Tavily fetch failure; URL retrieval cannot be self-handled"
    return False, "none", f"no normalizer for extension {ext!r}"


def _mineru_reason(size_mb, token_present):
    if size_mb is not None and size_mb > _MINERU_FREE_TIER_MB and not token_present:
        return (f"{size_mb:.1f} MB > {_MINERU_FREE_TIER_MB} MB free-tier; "
                f"no MINERU_API_TOKEN")
    if not token_present:
        return "MinerU free-tier subprocess failed; no MINERU_API_TOKEN"
    return "MinerU subprocess failed with token configured"
