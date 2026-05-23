# Ingest agent-extraction fallback — design

- **Date:** 2026-05-23
- **Status:** approved (design); pending implementation plan
- **Branch:** `claude/ingest-agent-fallback` (off `master`)

## Background

A bootstrapped wikiforge curator workspace defaults to MinerU's free tier
(10 MB / 20 pages per file) because the credentials interview (`bootstrap.md`
Step 8) is optional and `.forge/secrets/` is gitignored — a token never
propagates across clones, worktrees, or from the framework repo. In practice
any normal-sized arxiv PDF (e.g. MMMU at 17 MB, the Tuna-2 paper at 15 MB)
exceeds the free tier; ingest's current behavior is to block the queue entry
(`[!]`) and file a `request-human` of type `large-download`. The wiki is then
stuck until a human pastes a token or fetches a smaller copy.

This spec adds an **agent-extraction fallback**: when `normalize_source` fails,
the ingest agent — which has its own document-reading capabilities — extracts
the source itself, writes a `<stem>.converted/<stem>.md` that `normalize_source`
will idempotently reuse, and continues. The fallback covers every raw-source
format the agent can self-extract; what it cannot self-extract still blocks
and routes through `request-human` as today.

The fallback is the curator's safety net for transient MinerU failures (API
errors, network outages, oversize) and for the common no-token case. It is
not a replacement for MinerU when MinerU is available — MinerU output remains
preferred, and the prompt below gives the user a one-touch path to install a
token and re-run with MinerU.

## Goals

- Ingest never hard-blocks on a PDF, docx, pptx, xlsx, or HTML source that
  MinerU or markdownify could not convert, as long as the agent can read it.
- The credential-provisioning gap (no token in a fresh bootstrap) stops being
  a pipeline-stopper. Workspaces stay usable on the free tier; tokens upgrade
  fidelity, they don't gate liveness.
- A user who has a token can hand it to the agent mid-ingest in one step;
  the token is saved to `credentials.env` for the rest of the workspace's life.
- Existing `request-human` escalation is retained for the cases the agent
  genuinely cannot self-extract (legacy `.xls` OLE binaries, `.url/.weblink`
  fetches the agent can't fulfill, encrypted or pure-scanned-image PDFs).

## Non-goals

- No change to `normalize_source`'s public contract. It still routes by
  extension, still raises `NormalizeError` on failure, still idempotently
  reuses a non-empty sibling `.converted/` directory.
- No new third-party dependency. The new helpers use Python stdlib only
  (`zipfile`, `re`, `pathlib`).
- No change to the bundle, to schema, to page types, or to the edge-type
  vocabulary.
- No automated token discovery / no environment-variable scraping beyond
  what `credentials.load_credentials` already does.
- No change to bootstrap. The fallback is an `ingest`-time fix, not a
  bootstrap-time fix.

## Design

### 1. Coverage

Every format the agent can self-extract gets a fallback mechanism; the rest
keep their current `request-human` escalation.

| Raw type             | Primary path                | Agent self-extract fallback                                                                          |
| -------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------- |
| `.pdf`               | MinerU                      | Agent's native PDF reader, paginated ≤ 20 pages per call                                              |
| `.docx`              | MinerU                      | `unzip -p file.docx word/document.xml`, strip `<w:t>` runs                                            |
| `.pptx`              | MinerU                      | `unzip -p file.pptx ppt/slides/slide*.xml`, strip `<a:t>` runs, one section per slide                |
| `.xlsx`              | MinerU                      | `unzip -p file.xlsx xl/sharedStrings.xml` + `xl/worksheets/sheet*.xml`, emit tab-separated per sheet  |
| `.html`, `.htm`      | `markdownify` (offline)     | Agent reads the file as text and formats to markdown                                                  |
| `.xls` (legacy OLE)  | MinerU                      | None — binary format, not self-extractable → block + `request-human`                                  |
| `.url`, `.weblink`   | Tavily CLI                  | None — the failure is a fetch, not a convert → block + `request-human`                                |
| Repo dir, `.md/.txt` | None (already readable)     | n/a — `normalize_source` never raises for these                                                       |

### 2. Flow — rewrite of `ingest/SKILL.md` §3 "If normalization fails"

The current §3 says: on `NormalizeError`, set the queue entry to `[!]` blocked
and file a `request-human` (`type: large-download` for oversize PDF, `type:
paid-api` or `human-judgement` otherwise). Replace with:

1. Call `normalize_source(path)`. On success, proceed as today.
2. On `NormalizeError`, call the new helper
   `normalize.agent_extract_advice(path)` (see §4). The helper returns
   `(eligible: bool, mechanism: str, reason: str)`.
3. If `eligible` is `True` (`mechanism` is one of `pdf-read | unzip-officex |
   html-text`):
   - The agent self-extracts using the mechanism. For PDF that is a paginated
     read of ≤ 20 pages per call. For docx/pptx/xlsx it is a Bash `unzip -p`
     into a small XML-text strip. For html it is reading the file as text
     and emitting markdown.
   - Write the result to `<stem>.converted/<stem>.md` with a provenance
     header on the first line:
     ```
     <!-- converted: agent-extracted fallback (<mechanism>, reason: <reason>), <date> -->
     ```
   - Re-call `normalize_source(path)`; it returns the just-written markdown
     idempotently (existing behavior at `normalize.py:85`).
   - Run the user prompt described in §3.
4. If `eligible` is `False`, unchanged behavior: set the queue entry to
   `[!]`, file a `request-human` (`type: large-download` for `.xls`, `type:
   paid-api` for Tavily-fetched URL failures, `type: human-judgement`
   otherwise).
5. If the agent's self-extract in step 3 itself fails (encrypted PDF,
   corrupt zip, pure-scanned-image PDF needing OCR): fall through to step 4
   — block and file `request-human`.

A successful fallback does NOT mark the queue entry `[!]`; the source is
processed normally and the entry advances to `[x]` after page drafting.

### 3. The user prompt (after a successful fallback)

The agent prompts the user with two options:

- **Continue** — keep the agent-extracted conversion; ingest proceeds.
- **Provide a `MINERU_API_TOKEN`** — user pastes a token; agent calls
  `credentials.set_credential("MINERU_API_TOKEN", value)` to save it to
  `.forge/secrets/credentials.env`, then re-calls
  `normalize_source(path, force=True)` so MinerU now produces a clean
  conversion that overwrites the agent-extracted `<stem>.converted/`.

In a **headless** runtime (no human reachable), the agent skips the prompt
entirely: the self-extraction stands, and the agent appends one line to
`.forge/log.md`:

```
## [<UTC>] ingest | self-extracted <path> (<mechanism>, reason: <reason>); configure MINERU_API_TOKEN for higher-fidelity conversion
```

This is the headless equivalent of the warning — preserved in the curator
op log, picked up by the next interactive session.

### 4. Helpers — the tested code

#### `normalize.py` → `agent_extract_advice(raw_path) → (bool, str, str)`

Determines whether an `NormalizeError` is recoverable by an agent self-extract,
and provides a diagnostic string for the warning.

Returns `(eligible, mechanism, reason)`:

| Extension                | `eligible` | `mechanism`        | Example `reason`                                                       |
| ------------------------ | ---------- | ------------------ | ---------------------------------------------------------------------- |
| `.pdf`                   | True       | `pdf-read`         | `17.0 MB > 10 MB free-tier; no MINERU_API_TOKEN`                       |
| `.docx`, `.pptx`, `.xlsx`| True       | `unzip-officex`    | `25.3 MB > 10 MB free-tier; no MINERU_API_TOKEN`                       |
| `.html`, `.htm`          | True       | `html-text`        | `markdownify import failed: <msg>`                                     |
| `.xls`                   | False      | `none`             | `legacy OLE binary, not self-extractable`                              |
| `.url`, `.weblink`       | False      | `none`             | `Tavily fetch failure; URL retrieval cannot be self-handled`           |
| anything else            | False      | `none`             | `no normalizer for extension <ext>`                                    |

`reason` is best-effort, derived from file size, `credentials.load_credentials()`
return value, and the suffix of the file. It is used only for the warning
string in the prompt and the log line — it is not load-bearing for control
flow. Control flow uses `eligible` and `mechanism` only.

#### `credentials.py` → `set_credential(key, value, *, path=None)`

Writes a credential to `.forge/secrets/credentials.env` in place. Behavior:

- If a line matching `^\s*#?\s*<KEY>\s*=` exists, it is replaced with
  `<KEY>=<value>` (uncomment if commented, update value if not).
- Otherwise the line is appended to the end of the file with a trailing
  newline.
- All other lines (comments, blank lines, other keys) are preserved
  unchanged.
- An empty or whitespace-only `value` raises `ValueError` rather than
  writing `<KEY>=` (an uncommented empty key is worse than the commented
  default — it suppresses any environment-variable override the loader
  would otherwise apply).
- `path` defaults to the same module-anchored path
  `credentials.DEFAULT_PATH` already uses (`.forge/secrets/credentials.env`
  resolved relative to the module location, as fixed in commit `0527c3c`).
- The file is created with mode `0600` if it does not exist; if it exists,
  its mode is not changed.
- The function does not log the value; the agent prints only the key name
  back to the user for confirmation (matches bootstrap Step 8 discipline).

### 5. Provenance marker

Every `<stem>.converted/<stem>.md` produced by the fallback begins with the
HTML comment:

```
<!-- converted: agent-extracted fallback (<mechanism>, reason: <reason>), <YYYY-MM-DD> -->
```

This is read by no code (lint, ingest, build all treat it as inert markdown),
but a future curator session reading the converted file can tell at a glance
that this is not MinerU output and may be lower fidelity. If the user later
provides a token and re-runs with `force=True`, MinerU overwrites the file
and the marker is naturally replaced with MinerU's own first line.

## Testing

### Unit tests

- **`tests/test_normalize.py`** — add `test_agent_extract_advice_*` covering
  one case per row of the §4 table. Mock file size and token presence;
  assert `(eligible, mechanism)` exactly and assert `reason` contains the
  expected substring (so a future tweak to the diagnostic string does not
  break the test).
- **`tests/test_credentials.py`** — add `test_set_credential_*`:
  uncomment-existing-commented-key, update-existing-uncommented-key,
  append-new-key, preserve-other-lines, file-not-exists-creates-with-mode,
  empty-value-rejected. The "preserve other lines" test seeds a file with
  comments, blank lines, and a second key, then verifies all are byte-for-byte
  intact except the targeted line.

### Integration runbook

- **`tests/INTEGRATION_ingest.md`** — append a scenario "Oversize PDF
  fallback":
  - Start from a bootstrapped workspace with no `MINERU_API_TOKEN`.
  - Drop a >10 MB arxiv PDF in `raw/papers/`.
  - Run `ingest <path>`.
  - Expected: agent prints the §3 prompt with two options; on **Continue**,
    the queue entry advances to `[x]`, a `<stem>.converted/<stem>.md` exists
    with the §5 provenance marker, lint exits clean.
  - On **Provide a token** with a valid token: the marker line is replaced
    by MinerU's output, `.forge/secrets/credentials.env` carries
    `MINERU_API_TOKEN=...`, lint exits clean.

The agent-extraction step and the interactive prompt are not unit-testable
(they depend on the agent runtime); the runbook is the verification surface.

## Design-constraint #4 exception (explicit)

`PLAN_Init.md`'s guiding principles state that the human is a resource broker
and the only synchronous human interaction is the async, file-based
`request-human` protocol. The interactive prompt in §3 is a *synchronous
interrupt* and therefore a deliberate narrow exception:

- It fires only in interactive runtimes; headless runs degrade to a log line.
- It is bounded to one prompt with two options at the moment of fallback —
  not a per-page approval gate.
- The async `request-human` path remains in place for everything the agent
  cannot self-extract.

The exception is recorded here so it is an explicit decision, not a silent
drift. If a future change broadens the prompt or makes it fire outside the
fallback path, that requires a separate discussion.

## Files touched

- `/.forge/skills/ingest/SKILL.md` — rewrite of §3 "If normalization fails";
  small §3-bottom note pointing at the prompt and the headless log line.
- `/.forge/lib/normalize.py` — new helper `agent_extract_advice`.
- `/.forge/lib/credentials.py` — new helper `set_credential`.
- `/tests/test_normalize.py` — unit tests for `agent_extract_advice`.
- `/tests/test_credentials.py` — unit tests for `set_credential`.
- `/tests/INTEGRATION_ingest.md` — append the oversize-PDF scenario.

No change to `bin/wiki-*`, no change to `bootstrap.md`, no change to
`schema.md`, no change to the build script or templates.

## Out of scope (intentionally)

- Re-running `normalize_source` from inside `normalize.py` when MinerU fails.
  The control flow lives in the ingest skill so the agent (not Python) drives
  the self-extract; this keeps `normalize.py` a clean MinerU/markdownify/Tavily
  router.
- Detecting page-count limits before calling MinerU. Page-counting requires
  parsing the PDF, which adds a dependency. The reactive catch handles it
  uniformly with size-based failures.
- A new request-human request type for "missing API token". The §3 prompt
  closes the loop without it; the headless log line surfaces the same
  information asynchronously.
- Touching `xls` legacy binary or `url/weblink` fetch failures. These remain
  on the `request-human` path.
- Any change to ingest's queue-state vocabulary (`[ ] [~] [x] [!]`) or to
  how `find_ingested_source` dedups by `content_hash`.
