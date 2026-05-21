---
name: wikiforge-ingest
description: Turn a raw source (paper, repo, doc, web clip, note) into one or more wiki pages with valid frontmatter. Default single-file mode; supports queue scan.
---

# ingest — raw → wiki

You are turning a raw source into wiki pages. Each invocation handles one source (default) or processes a queue of pending sources.

## Modes

- **`ingest <path>`** — process exactly this source. The path is relative to the workspace root and lives somewhere under `raw/`.
- **`ingest --scan`** — walk `raw/` with `ingest_helpers.scan_raw()`, find sources not already in `.forge/queue.md` or `wiki/sources/`, append them as `[ ]` entries with `ingest_helpers.append_queue_entry()`, then process pending entries.
- **`ingest --queue`** — process existing pending entries in `.forge/queue.md` without scanning.
- **`ingest`** (no args) — ask the human: "scan, or specific path?" (interactive only)

## Workflow for one source

Repeat for every source you process:

### 1. Check for prior ingestion

```python
from ingest_helpers import content_hash
h = content_hash("raw/papers/foo.pdf")          # "sha256:abc123..."
```

`content_hash` accepts a file *or* a repo directory — for a `raw/repos/<org>/<repo>@<sha>/` directory it hashes a manifest of the contained files (relative paths + sizes, `.git` excluded), so repos dedup exactly like every other source.

Use `ingest_helpers.find_ingested_source(content_hash=h)` to look for an existing `wiki/sources/` page with that hash (it also accepts `source_path=` to match by raw path):

```python
from ingest_helpers import find_ingested_source
hit = find_ingested_source(content_hash=h)   # -> (slug, frontmatter) or None
```

- **Same hash → skip.** Append a one-line log entry to `wiki/log.md` and move on.
- **Different hash on a page with the same `source_path:` → re-ingest.** The source changed.
- **No matching page → proceed.**

### 2. Identify source type

Use `ingest_helpers.detect_source_type(path)` or eyeball the location:

| Path under          | Type     |
| ------------------- | -------- |
| `raw/papers/`       | paper    |
| `raw/repos/`        | repo     |
| `raw/docs/`         | doc      |
| `raw/web/`          | web      |
| `raw/notes/`        | note     |

For repos, the directory layout is always `raw/repos/<org>/<repo>@<sha>/`. The `<org>/<repo>` and `<sha>` go into `code-patterns/` page provenance verbatim.

### 3. Normalize the source to markdown

Raw sources arrive in many formats. Before reading, convert the artifact to
markdown with the normalizer. It routes by file type and writes output to a
sibling `<stem>.converted/` directory — the original raw file is left in place,
untouched.

```python
from normalize import normalize_source, NormalizeError
try:
    readable = normalize_source("raw/papers/foo.pdf")   # -> Path to markdown
except NormalizeError as e:
    ...   # see "If normalization fails" below
```

| Raw type (location)                  | Tool the normalizer uses          |
| ------------------------------------ | --------------------------------- |
| `raw/papers/*.pdf`                    | MinerU (PDF → markdown + images)  |
| `raw/docs/*.{pdf,docx,pptx,xls,xlsx}` | MinerU                            |
| `raw/web/*.{html,htm}`                | markdownify (offline, local)      |
| `raw/web/*.url` (file holding a URL)  | Tavily CLI (`tvly extract`)       |
| `raw/notes/*.{md,txt}`                | none — already readable, returned as-is |
| `raw/repos/<org>/<repo>@<sha>/`       | none — a directory, returned as-is |

MinerU uses the free agent API (10MB / 20 pages per file) unless
`MINERU_API_TOKEN` is set in `.forge/secrets/credentials.env`, which unlocks the
precision API (200MB / 200 pages). The Tavily path needs `TAVILY_API_KEY` in the
same file. `normalize_source` loads `.forge/secrets/credentials.env`
automatically — you do not load it yourself.

**If normalization fails** (`NormalizeError`) — e.g. a PDF over the free-tier
limit with no token, or the Tavily CLI not installed — do NOT draft a page from
an unreadable source. Set the queue entry to `[!]` blocked
(`ingest_helpers.set_queue_state(queue_path, source_path, "!", note="req <id>")`)
and write a request via the request-human skill (`type: large-download` for an
oversize PDF, `type: paid-api` or `human-judgement` otherwise).

### 4. Read the source

- **Papers / docs:** read the converted markdown that `normalize_source`
  returned. Figures are in the sibling `images/` directory if you need them.
- **Repos:** start with `README` and any top-level config files. Use
  `ingest_helpers.enumerate_repo_files(repo_root)` for an ordered list of
  "interesting" files. Read selectively — not the whole repo.
- **Web:** read the converted markdown.
- **Notes:** `normalize_source` returns the note path unchanged — read it
  directly.

### 5. Gather context

Before drafting pages, read:

- `wiki/manifest.md` (current scope and top topics)
- `wiki/out_of_scope.md` (what to avoid)
- `wiki/index.md` (existing pages — for dedup and cross-link targets)
- Any pages your source claims overlap with (use `bin/wiki-search` to find them)

### 6. Draft pages

Always draft a `wiki/sources/<slug>.md`, even for trivial sources. The source page is the agent's read of what the source contributes.

Conditional drafts (only when warranted by the source):

| Source type | Likely to draft / update                                |
| ----------- | ------------------------------------------------------- |
| paper       | `concepts/`, `claims/`, `entities/`                     |
| repo        | `code-patterns/` (with provenance), maybe `entities/`   |
| doc         | `conventions/`                                          |
| web         | varies by content                                       |
| note        | varies; usually `concepts/` or `conventions/`           |

**For `code-patterns/`:** the frontmatter MUST carry `repo`, `commit`, `path`, `lines`, `language`. Do NOT embed the code in the page body — the build step extracts it from `raw/repos/` at build time and writes to `wiki/snippets/`. Cite specific line ranges (e.g., `lines: "10-45"`).

**Cross-references:**
- Use plain `[[wikilinks]]` in prose for routine references. These are cheap and improve the backlink graph.
- Add a typed relationship to frontmatter (`extends:`, `contradicts:`, `supersedes:`, `implements:`) only when the source clearly establishes that relationship — never speculatively.
- Schema enforces which page types may declare which edge types. See `schema.md` for the matrix. When in doubt, prefer a plain wikilink over a wrong typed edge.

**Frontmatter discipline (this is what the linter checks):**
- Every page needs `title`, `type`, `created`, `last_verified`, `confidence` (one of: verified, likely, low, placeholder, refuted).
- `confidence:` is honest. If the source is your only evidence, `likely` at best. If you couldn't fully verify, `low`. If you're stubbing pending more reading, `placeholder`.
- `claims/` pages need non-empty `evidence:` OR `counter_evidence:`. An empty pair is a hard error.
- `code-patterns/` pages need full provenance and the cited file must actually exist in `raw/repos/<repo>@<sha>/<path>`.

### 7. Update meta files

- Append to `wiki/log.md`: `## [YYYY-MM-DD] ingest | <source-slug>` plus a one-line note.
- Regenerate the wiki index. Running `python3 .forge/lib/lint.py --fix` is the
  recommended close-out: it rebuilds both `wiki/index.md` and the `wiki/.meta/`
  index that `query` reads. (`python3 .forge/lib/index.py` does the same index
  rebuild — both `index.md` and `wiki/.meta/` — without running the lint
  checks.) This is not optional — pages you ingested are not searchable until
  the index is rebuilt.

### 8. Update the queue

If the source was queued:
- Change `[ ]` → `[x]` when done, or `[~]` while in progress, or `[!]` if blocked (with a request id).

Use `ingest_helpers.set_queue_state(queue_path, source_path, "x")`.

### 9. Surface follow-ups

If the source cites other sources you don't have:
- Publicly fetchable (arxiv, github, public docs) → add a note to `.forge/queue.md` for the explorer to pick up. Don't fetch inline.
- Paywalled or credentialed → write a request to `.forge/requests/inbox/<id>.md` (see request-human skill).

If the source contradicts an existing wiki page:
- Note it in your `sources/<slug>.md` body under a `## Contradictions` heading.
- Consider whether to add a `contradicts:` frontmatter edge on a `claims/` page.
- Do NOT silently overwrite the existing page. Flag it for the human curator via `.forge/log.md`.

## Frontmatter cheatsheet

Encode this so pages pass lint on the first try. The full spec is `schema.md`;
this is the compressed version ingest needs in hand.

**Every page** requires: `title`, `type`, `created` (YYYY-MM-DD),
`last_verified` (YYYY-MM-DD), `confidence`
(`verified` | `likely` | `low` | `placeholder` | `refuted`).

Per-type extra required fields and the edge types each type may declare in
frontmatter:

| Type           | Extra required fields                                                    | Frontmatter edges allowed              |
| -------------- | ------------------------------------------------------------------------ | -------------------------------------- |
| `concept`      | —                                                                        | none                                   |
| `convention`   | —                                                                        | none                                   |
| `code-pattern` | `repo`, `commit` (40-char sha), `path`, `lines`, `language`               | `supersedes`, `implements`             |
| `claim`        | `status` (`validated`\|`likely`\|`open`\|`refuted`), `evidence`, `counter_evidence` | `extends`, `contradicts`, `supersedes` |
| `source`       | `source_type` (`paper`\|`repo`\|`doc`\|`web`\|`note`), `source_path`, `content_hash` | none                          |
| `entity`       | `entity_type` (`person`\|`lab`\|`project`\|`tool`\|`organization`)        | none                                   |

Rules the linter enforces — get these right up front:

- A `claim` with **both** `evidence:` and `counter_evidence:` empty is a hard
  error. At least one must be non-empty.
- Declaring an edge type not in the "allowed" column is a `disallowed-edge-type`
  error. When unsure, prefer a plain prose `[[wikilink]]` (always allowed, emits
  a `references` edge).
- A `code-pattern`'s `repo` / `commit` / `path` must resolve to a real file at
  `raw/repos/<org>/<repo>@<commit>/<path>`, or lint reports `excerpt-missing`.
- Slugs are unique across **all** types — `concepts/foo` and `claims/foo`
  collide (`duplicate-slug` error).
- `confidence` is honest: a single source supports `likely` at best; unverified
  synthesis is `low`; a stub pending more reading is `placeholder`.

On a `claim`, `confidence` and `status` are independent axes. `confidence` is
how sure you are the page is *accurate as written*; `status` is the claim's
standing *in the field* (`validated` | `likely` | `open` | `refuted`). A page
that accurately documents a genuine `open` controversy can still be
`confidence: verified` — do not force the two values to track each other.

## Lint before you stop

After each ingest run, execute:

```sh
python3 .forge/lib/lint.py --report
```

That run also refreshes `.forge/lint-report.md` — the health snapshot the next
`explorer` pass reads.

Address every error you introduced. Warnings can wait — but errors block the next build. If the linter reports `excerpt-missing` on a `code-patterns/` page you just wrote, the cited file path doesn't resolve in `raw/repos/`. Fix the provenance.

## What ingest is **not**

- Not a paper-summarizer service. The source page is a curator note, not a comprehensive abstract.
- Not a code-pasting service. Excerpts come from `raw/repos/` at build time. Your page body describes *why* and *when to use*, not what the code says line by line.
- Not authoritative. Every page carries `confidence:`, and `last_verified:` is a date you owe honesty about. When a future session re-reads the source and finds you got something wrong, that's the system working — update the page and bump `last_verified`.

## See also

- `schema.md` — page-type spec (frontmatter requirements per type)
- `.forge/lib/normalize.py` — how raw artifacts of each type become markdown
- `.forge/lib/credentials.py` — how tool tokens are loaded from `.forge/secrets/`
- `.forge/skills/lint/SKILL.md` — what mechanical errors look like
- `.forge/skills/request-human/SKILL.md` — how to ask for what you can't fetch
- `.forge/skills/explorer/SKILL.md` — what runs *between* ingest invocations to keep the queue full
