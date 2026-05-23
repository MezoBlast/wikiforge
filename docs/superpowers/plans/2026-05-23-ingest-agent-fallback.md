# Ingest agent-extraction fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `normalize_source` cannot produce markdown (oversize for the MinerU free tier, transient API failure, markdownify failure), the ingest agent self-extracts the file and `normalize_source` idempotently reuses the result; on an interactive runtime the user is offered a one-touch path to install a `MINERU_API_TOKEN` and re-run with MinerU.

**Architecture:** Two small new helpers (`credentials.set_credential` for writing a key to `credentials.env` safely, `normalize.agent_extract_advice` for classifying a `NormalizeError` as agent-recoverable or escalation-only) plus a rewrite of `ingest/SKILL.md` §3 that wires them together. `normalize_source` itself is unchanged.

**Tech Stack:** Python 3 stdlib only (`re`, `pathlib`, `zipfile` via the agent at runtime); pytest with `tmp_path` and `monkeypatch` fixtures.

**Spec:** `docs/superpowers/specs/2026-05-23-ingest-agent-fallback-design.md`.

**Worktree:** `worktrees/ingest-fallback` on branch `claude/ingest-agent-fallback` (off `master`). If executing in a fresh session, attach to it or create a new worktree on the same branch via `superpowers:using-git-worktrees` first.

---

## Task 1: `credentials.set_credential`

**Files:**
- Modify: `.forge/lib/credentials.py`
- Test: `tests/test_credentials.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_credentials.py`:

```python
import stat

import pytest


def test_set_credential_uncomments_commented_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# MINERU_API_TOKEN=\n# TAVILY_API_KEY=\n")
    credentials.set_credential("MINERU_API_TOKEN", "abc123", path=f)
    text = f.read_text()
    assert "MINERU_API_TOKEN=abc123\n" in text
    # The OTHER commented line is preserved exactly.
    assert "# TAVILY_API_KEY=\n" in text


def test_set_credential_updates_existing_uncommented_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("MINERU_API_TOKEN=old\n")
    credentials.set_credential("MINERU_API_TOKEN", "new", path=f)
    assert f.read_text() == "MINERU_API_TOKEN=new\n"


def test_set_credential_appends_new_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("OTHER=foo\n")
    credentials.set_credential("NEW_KEY", "bar", path=f)
    text = f.read_text()
    assert "OTHER=foo\n" in text
    assert "NEW_KEY=bar\n" in text


def test_set_credential_preserves_other_lines(tmp_path):
    f = tmp_path / "c.env"
    seed = "# header comment\n\nFIRST=1\n# commented note\nSECOND=2\n"
    f.write_text(seed)
    credentials.set_credential("SECOND", "two", path=f)
    text = f.read_text()
    assert "# header comment\n" in text
    assert "\n\n" in text             # blank line preserved
    assert "FIRST=1\n" in text
    assert "# commented note\n" in text
    assert "SECOND=two\n" in text
    assert "SECOND=2\n" not in text   # old value gone


def test_set_credential_empty_value_rejected(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    with pytest.raises(ValueError):
        credentials.set_credential("K", "", path=f)


def test_set_credential_whitespace_value_rejected(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    with pytest.raises(ValueError):
        credentials.set_credential("K", "   ", path=f)


def test_set_credential_creates_file_with_secure_mode(tmp_path):
    f = tmp_path / "fresh.env"
    assert not f.exists()
    credentials.set_credential("K", "v", path=f)
    assert f.read_text() == "K=v\n"
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o600


def test_set_credential_does_not_change_existing_file_mode(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    os.chmod(f, 0o644)
    credentials.set_credential("K", "v", path=f)
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o644
```

`os`, `Path`, `credentials` are already imported at the top of this test module — do not re-import them.

- [ ] **Step 2: Run the new tests; expect failure**

Run from the worktree root:

```bash
python3 -m pytest tests/test_credentials.py -k set_credential -v
```

Expected: **8 ERRORS**, all of the form `AttributeError: module 'credentials' has no attribute 'set_credential'`.

- [ ] **Step 3: Implement `set_credential`**

Edit `.forge/lib/credentials.py`. Add `import re` near the top (alongside `import os` and `from pathlib import Path`). Append the function at the bottom of the file:

```python
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
```

- [ ] **Step 4: Run the tests; expect pass**

```bash
python3 -m pytest tests/test_credentials.py -v
```

Expected: every test in the file passes — the 8 new `set_credential` tests plus the existing tests for `parse_env`, `load_credentials`, and `DEFAULT_PATH`. Zero failures.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/credentials.py tests/test_credentials.py
git commit -m "$(cat <<'EOF'
feat(credentials): set_credential — write a key to credentials.env

Uncomments an existing commented key, updates an existing uncommented key,
or appends a new one. Refuses empty values (an uncommented empty key would
suppress the environment-variable override the loader honors).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `normalize.agent_extract_advice`

**Files:**
- Modify: `.forge/lib/normalize.py`
- Test: `tests/test_normalize.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_normalize.py`. `normalize`, `pytest`, `Path` are already imported.

```python
def test_agent_extract_advice_pdf_oversize_no_token(tmp_path, monkeypatch):
    p = tmp_path / "big.pdf"
    p.write_bytes(b"x" * (11 * 1024 * 1024))   # 11 MB > 10 MB
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "10 MB" in reason
    assert "MINERU_API_TOKEN" in reason


def test_agent_extract_advice_pdf_small_no_token(tmp_path, monkeypatch):
    p = tmp_path / "small.pdf"
    p.write_bytes(b"x" * 1024)
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "MINERU_API_TOKEN" in reason


def test_agent_extract_advice_pdf_token_present(tmp_path, monkeypatch):
    p = tmp_path / "p.pdf"
    p.write_bytes(b"x" * 1024)
    monkeypatch.setattr(normalize, "load_credentials",
                        lambda **kw: {"MINERU_API_TOKEN": "tok123"})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "token" in reason.lower()


def test_agent_extract_advice_docx(tmp_path, monkeypatch):
    p = tmp_path / "f.docx"
    p.write_bytes(b"PK\x03\x04")   # zip magic
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_pptx(tmp_path, monkeypatch):
    p = tmp_path / "f.pptx"
    p.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_xlsx(tmp_path, monkeypatch):
    p = tmp_path / "f.xlsx"
    p.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_html(tmp_path, monkeypatch):
    p = tmp_path / "page.html"
    p.write_text("<p>hi</p>")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "html-text")


def test_agent_extract_advice_htm(tmp_path, monkeypatch):
    p = tmp_path / "page.htm"
    p.write_text("<p>hi</p>")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "html-text")


def test_agent_extract_advice_xls(tmp_path, monkeypatch):
    p = tmp_path / "f.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0")   # OLE magic
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert ("ole" in reason.lower()) or ("legacy" in reason.lower())


def test_agent_extract_advice_url(tmp_path, monkeypatch):
    p = tmp_path / "x.url"
    p.write_text("https://example.com\n")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert ("tavily" in reason.lower()) or ("fetch" in reason.lower())


def test_agent_extract_advice_weblink(tmp_path, monkeypatch):
    p = tmp_path / "x.weblink"
    p.write_text("https://example.com\n")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (False, "none")


def test_agent_extract_advice_unknown_extension(tmp_path, monkeypatch):
    p = tmp_path / "thing.xyz"
    p.write_text("data")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert "no normalizer" in reason.lower()
```

- [ ] **Step 2: Run the new tests; expect failure**

```bash
python3 -m pytest tests/test_normalize.py -k agent_extract_advice -v
```

Expected: **12 ERRORS**, all `AttributeError: module 'normalize' has no attribute 'agent_extract_advice'`.

- [ ] **Step 3: Implement `agent_extract_advice`**

Edit `.forge/lib/normalize.py`. Add two module-level constants beneath the existing `*_EXTS` sets:

```python
_AGENT_OFFICEX_EXTS = {".docx", ".pptx", ".xlsx"}
_MINERU_FREE_TIER_MB = 10
```

Append the function (and its two small helpers) at the bottom of the file:

```python
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
        return True, "html-text", "markdownify path failed (offline converter)"
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
```

- [ ] **Step 4: Run the new tests, then the whole suite**

```bash
python3 -m pytest tests/test_normalize.py -k agent_extract_advice -v
python3 -m pytest tests/ -q
```

Expected: the 12 new tests pass; the whole suite reports `92 passed` (72 prior + 8 from Task 1 + 12 new). Zero failures.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/normalize.py tests/test_normalize.py
git commit -m "$(cat <<'EOF'
feat(normalize): agent_extract_advice — classify NormalizeError recoverability

Returns (eligible, mechanism, reason) so the ingest agent can decide between
a self-extract fallback (pdf-read / unzip-officex / html-text) and the
existing request-human escalation (xls / url / unknown).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Rewrite `ingest/SKILL.md` §3 "If normalization fails"

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md`

- [ ] **Step 1: Locate the current "If normalization fails" paragraph**

```bash
grep -n 'If normalization fails' .forge/skills/ingest/SKILL.md
```

Expected: one match in §3 "Normalize the source to markdown" (the paragraph that currently begins "**If normalization fails** (`NormalizeError`) — e.g. a PDF over the free-tier limit ..."). That paragraph and its bullet are the entire region you are replacing.

- [ ] **Step 2: Replace the paragraph with the new fallback flow**

Replace the single paragraph beginning **"If normalization fails"** (and any immediately following lines that belong to that paragraph, up to the start of the next section "### 4. Read the source") with the block below. Do not touch §3's intro, the routing table, the `normalize_source` example, or the MinerU credential note above it.

```markdown
**If normalization fails** (`NormalizeError`), the ingest agent consults
`normalize.agent_extract_advice(path)` and either self-extracts or escalates.

```python
from normalize import normalize_source, NormalizeError, agent_extract_advice

try:
    readable = normalize_source(path)
except NormalizeError:
    eligible, mechanism, reason = agent_extract_advice(path)
    if eligible:
        # self-extract per `mechanism` (see table below), write
        # <stem>.converted/<stem>.md, then re-call normalize_source(path)
        ...
    else:
        # set queue entry [!] + request-human (escalation table below)
        ...
```

#### Agent self-extract fallback

When `eligible` is True, perform the self-extract for the named `mechanism`,
write `<stem>.converted/<stem>.md` whose first line is the provenance header

```
<!-- converted: agent-extracted fallback (<mechanism>, reason: <reason>), <YYYY-MM-DD> -->
```

then re-call `normalize_source(path)`; it idempotently returns the just-written
markdown (existing `<stem>.converted/` reuse path).

| `mechanism`     | What the agent does                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------- |
| `pdf-read`      | Use the agent's native PDF read tool; paginate ≤ 20 pages per call; concatenate to one markdown body.     |
| `unzip-officex` | `unzip -p file.docx word/document.xml` (or `ppt/slides/slide*.xml`, or `xl/sharedStrings.xml` + `xl/worksheets/sheet*.xml`); strip XML to text — `<w:t>` for docx, `<a:t>` for pptx (one section per slide), tab-separated rows per sheet for xlsx. |
| `html-text`     | Read the file as text; emit markdown — headings, body, basic tables.                                      |

If the agent's own extraction fails (encrypted PDF, corrupt zip, pure-scanned
PDF needing OCR), fall through to the escalation block below — do not draft a
page from an unreadable source.

After a successful self-extract:

- **Interactive runtime** — prompt the user with two options:
  - **Continue** — keep the agent-extracted conversion; ingest proceeds.
  - **Provide a `MINERU_API_TOKEN`** — user pastes a token; call
    `credentials.set_credential("MINERU_API_TOKEN", value)` to save it to
    `.forge/secrets/credentials.env`, then re-call
    `normalize_source(path, force=True)` so MinerU overwrites the
    agent-extracted conversion with a higher-fidelity one.
- **Headless runtime (no human reachable)** — skip the prompt; append one
  line to `.forge/log.md`:

  ```
  ## [<UTC>] ingest | self-extracted <path> (<mechanism>, reason: <reason>); configure MINERU_API_TOKEN for higher-fidelity conversion
  ```

#### Escalation (no self-extract path)

When `agent_extract_advice` returns `eligible=False` — `.xls` legacy binary,
`.url/.weblink` fetch failures, or unknown extensions — set the queue entry
to `[!]` blocked
(`ingest_helpers.set_queue_state(queue_path, source_path, "!", note="req <id>")`)
and file a request via the request-human skill:

- `type: large-download` for an oversize `.xls`,
- `type: paid-api` for a Tavily-fetched URL failure,
- `type: human-judgement` otherwise.
```

- [ ] **Step 3: Verify nothing else regressed**

```bash
python3 -m pytest tests/ -q
grep -n 'large-download\|request-human\|agent_extract_advice' .forge/skills/ingest/SKILL.md
```

Expected: `92 passed` (no new tests were added in this task, so the count is unchanged from Task 2's exit state). The grep should show `large-download` exactly once (now under `.xls`, not `.pdf`), `request-human` referenced from the escalation block, and `agent_extract_advice` referenced from both the python example and the prose.

- [ ] **Step 4: Commit**

```bash
git add .forge/skills/ingest/SKILL.md
git commit -m "$(cat <<'EOF'
docs(skill): ingest fallback — agent self-extract before request-human

Rewrite §3 "If normalization fails" to route a NormalizeError through
agent_extract_advice. PDF / docx / pptx / xlsx / html become agent
self-extracts that write <stem>.converted/ and reuse normalize_source.
Interactive runtimes prompt Continue / Provide-token; headless logs.
xls / url remain on the request-human path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Append integration runbook scenario

**Files:**
- Modify: `tests/INTEGRATION_ingest.md`

- [ ] **Step 1: Find the insertion point**

```bash
tail -1 tests/INTEGRATION_ingest.md
wc -l tests/INTEGRATION_ingest.md
```

Confirm the file ends with a newline; you will append a new top-level scenario after the existing content.

- [ ] **Step 2: Append the scenario**

Append to `tests/INTEGRATION_ingest.md`:

```markdown
## Scenario: Oversize PDF fallback (agent self-extract)

**Setup:**
1. Start from a freshly bootstrapped workspace with no MINERU_API_TOKEN
   configured — the seeded `.forge/secrets/credentials.env` has the
   `# MINERU_API_TOKEN=` line commented out.
2. Place an arxiv PDF larger than 10 MB at `raw/papers/<id>.pdf`. The MMMU
   paper at 17 MB is a representative case:
   `curl -sLo raw/papers/2311.16502.pdf https://arxiv.org/pdf/2311.16502`.
3. Invoke `ingest raw/papers/<id>.pdf`.

**Expected — Continue path (interactive):**

- `normalize_source` raises NormalizeError; the agent calls
  `agent_extract_advice` and gets `(True, "pdf-read", "<size> MB > 10 MB ...; no MINERU_API_TOKEN")`.
- The agent reads the PDF paginated and writes
  `raw/papers/<id>.converted/<id>.md`. Its first line is
  `<!-- converted: agent-extracted fallback (pdf-read, reason: ...), <date> -->`.
- The agent prompts: "<file> exceeded MinerU's free tier; I self-extracted
  it. Continue, or provide a MINERU_API_TOKEN to retry with MinerU?".
- User picks **Continue**.
- The queue entry advances to `[x]`; `wiki/sources/<slug>.md` is drafted
  normally.
- `python3 .forge/lib/lint.py --strict` exits 0.

**Expected — Provide-token path (interactive):**

- Same setup; user picks **Provide a MINERU_API_TOKEN** and pastes a token.
- Agent calls `credentials.set_credential("MINERU_API_TOKEN", <value>)`;
  `.forge/secrets/credentials.env` now carries an uncommented
  `MINERU_API_TOKEN=<value>` line (verify the key by name; never paste a real
  token into this runbook).
- Agent re-calls `normalize_source(path, force=True)`; MinerU overwrites
  `raw/papers/<id>.converted/<id>.md`. Its first line is now MinerU's own
  output, not the agent-extracted provenance header.
- Queue entry `[x]`; lint exits 0.

**Expected — Headless path (no interactive prompt available):**

- Same setup; the agent runtime has no way to prompt the user.
- The agent does NOT prompt. It keeps the self-extracted conversion.
- `.forge/log.md` carries one new line:
  `## [<UTC>] ingest | self-extracted <path> (pdf-read, reason: ...); configure MINERU_API_TOKEN for higher-fidelity conversion`.
- Queue entry `[x]`; lint exits 0.

**Negative case — `.xls` legacy file:**

- Drop a `.xls` file in `raw/docs/`. `normalize_source` raises NormalizeError;
  `agent_extract_advice` returns `(False, "none", "legacy OLE binary, ...")`.
- The queue entry is set to `[!]`; a `request-human` entry of type
  `large-download` is written to `.forge/requests/inbox/`. No `.converted/`
  is produced. Lint exits 0 (the source is blocked, not corrupt).
```

- [ ] **Step 3: Commit**

```bash
git add tests/INTEGRATION_ingest.md
git commit -m "$(cat <<'EOF'
test(ingest): integration runbook for oversize-PDF agent fallback

Continue / Provide-token / Headless / xls-escalation scenarios.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

After Task 4 is committed:

- [ ] **Step 1: Full test suite is green**

```bash
python3 -m pytest tests/ -q
```

Expected: every prior test plus the 8 new `set_credential` tests plus the 12 new `agent_extract_advice` tests pass; 0 failures.

- [ ] **Step 2: Branch is clean and ahead of master by 4 commits**

```bash
git status --short
git log --oneline master..HEAD
```

Expected: empty `git status` (no uncommitted edits) and five commits on `claude/ingest-agent-fallback` ahead of `master`: the spec commit already on the branch (`docs: design spec for ingest agent-extraction fallback`) plus four feature commits — one each from Tasks 1, 2, 3, 4 (`feat(credentials)`, `feat(normalize)`, `docs(skill)`, `test(ingest)`).

- [ ] **Step 3: Hand back to the user**

Report: branch ready for review on `claude/ingest-agent-fallback`. Do not merge to `master` or push to a remote without explicit user approval.
