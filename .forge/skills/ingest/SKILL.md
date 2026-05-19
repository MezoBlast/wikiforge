---
name: wikiforge-ingest
description: Turn a raw source (paper, repo, doc, web clip, note) into one or more wiki pages with valid frontmatter. Default single-file mode; supports queue scan.
---

# ingest — raw → wiki

You are turning a raw source into wiki pages. Each invocation handles one source (default) or processes a queue of pending sources.

## Modes

- **`ingest <path>`** — process exactly this source. The path is relative to the workspace root and lives somewhere under `raw/`.
- **`ingest --scan`** — walk `raw/`, find files not already in `.forge/queue.md` or `wiki/sources/`, append them as `[ ]` entries, then process pending entries.
- **`ingest --queue`** — process existing pending entries in `.forge/queue.md` without scanning.
- **`ingest`** (no args) — ask the human: "scan, or specific path?" (interactive only)

## Workflow for one source

Repeat for every source you process:

### 1. Check for prior ingestion

```python
from ingest_helpers import content_hash
h = content_hash("raw/papers/foo.pdf")          # "sha256:abc123..."
```

Look in `wiki/sources/` for any page whose frontmatter `content_hash:` equals `h`.

- **Same hash → skip.** Append a one-line log entry to `.forge/log.md` and move on.
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

### 3. Read the source

- **Papers (PDF):** read directly via your Read tool. If you can't extract text, write a request to `.forge/requests/inbox/` with `type: pdf-text-extraction` and `urgency: blocking`. Don't attempt to draft a page from an unreadable source.
- **Repos:** start with `README` and any top-level config files. Use `ingest_helpers.enumerate_repo_files(repo_root)` for an ordered list of "interesting" files. Read selectively — not the whole repo.
- **Docs / web:** read directly. They should already be plain markdown if extracted properly.
- **Notes:** read directly.

### 4. Gather context

Before drafting pages, read:

- `wiki/manifest.md` (current scope and top topics)
- `wiki/out_of_scope.md` (what to avoid)
- `wiki/index.md` (existing pages — for dedup and cross-link targets)
- Any pages your source claims overlap with (use `bin/wiki-search` to find them)

### 5. Draft pages

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

### 6. Update meta files

- Append entries to `wiki/index.md` for any new pages you created. (Or run `python3 .forge/lib/lint.py --fix` at the end to rebuild it.)
- Append to `wiki/log.md`: `## [YYYY-MM-DD] ingest | <source-slug>` plus a one-line note.

### 7. Update the queue

If the source was queued:
- Change `[ ]` → `[x]` when done, or `[~]` while in progress, or `[!]` if blocked (with a request id).

Use `ingest_helpers.set_queue_state(queue_path, source_path, "x")`.

### 8. Surface follow-ups

If the source cites other sources you don't have:
- Publicly fetchable (arxiv, github, public docs) → add a note to `.forge/queue.md` for the explorer to pick up. Don't fetch inline.
- Paywalled or credentialed → write a request to `.forge/requests/inbox/<id>.md` (see request-human skill).

If the source contradicts an existing wiki page:
- Note it in your `sources/<slug>.md` body under a `## Contradictions` heading.
- Consider whether to add a `contradicts:` frontmatter edge on a `claims/` page.
- Do NOT silently overwrite the existing page. Flag it for the human curator via `.forge/log.md`.

## Lint before you stop

After each ingest run, execute:

```sh
python3 .forge/lib/lint.py --report
```

Address every error you introduced. Warnings can wait — but errors block the next build. If the linter reports `excerpt-missing` on a `code-patterns/` page you just wrote, the cited file path doesn't resolve in `raw/repos/`. Fix the provenance.

## What ingest is **not**

- Not a paper-summarizer service. The source page is a curator note, not a comprehensive abstract.
- Not a code-pasting service. Excerpts come from `raw/repos/` at build time. Your page body describes *why* and *when to use*, not what the code says line by line.
- Not authoritative. Every page carries `confidence:`, and `last_verified:` is a date you owe honesty about. When a future session re-reads the source and finds you got something wrong, that's the system working — update the page and bump `last_verified`.

## See also

- `schema.md` — page-type spec (frontmatter requirements per type)
- `.forge/skills/lint/SKILL.md` — what mechanical errors look like
- `.forge/skills/request-human/SKILL.md` — how to ask for what you can't fetch
- `.forge/skills/explorer/SKILL.md` — what runs *between* ingest invocations to keep the queue full
