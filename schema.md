# schema.md — wiki page specifications

This file is the **definitive** specification for what a valid wiki page looks like. Every other skill (ingest, query, lint, build, explorer) reads this and must conform.

Changes to this file are schema-breaking. Bump the schema version when modifying.

```yaml
schema_version: 1
```

---

## Page types

Six types, fixed in v1. Adding a seventh requires a new section here, a new lint rule, and explicit discussion.

| Type             | Directory          | Purpose                                                 |
| ---------------- | ------------------ | ------------------------------------------------------- |
| concept          | `wiki/concepts/`   | **Residual.** Abstract knowledge not covered by another type: general theory/definitions, or an entity's internal structure (taxonomy, results, pipeline, metric mechanism). |
| convention       | `wiki/conventions/`| An abstract normative practice — how the field conducts/reports evaluation (protocol, scoring scale, judging paradigm, aggregation rule). |
| code-pattern     | `wiki/code-patterns/` | Canonical code with hard provenance.                 |
| claim            | `wiki/claims/`     | Testable assertions with evidence + counter-evidence.   |
| source           | `wiki/sources/`    | One summary per ingested raw source.                    |
| entity           | `wiki/entities/`   | An embodied artifact (model, dataset, benchmark-project, tool — has weights/data/repo) or a real person/lab/organization. |

Subdirectories within a type are permitted (e.g., `wiki/concepts/optimization/sgd.md`). A page's **slug** is the path inside `wiki/` minus `.md` (e.g., `concepts/optimization/sgd`).

---

## Choosing a page type

Pick a page's type with this **priority-ordered procedure — first match wins.**
The specific types are checked *before* `concept`; `concept` is the **residual**,
reached only when 1–5 do not apply. This ordering is deliberate — it stops
`concept` from becoming a catch-all.

1. **source** — the raw artifact you are ingesting (one per source, always).
2. **code-pattern** — canonical code you can pin to `repo` + `commit` + `path` +
   `lines`; a *located excerpt* of an implementation.
3. **claim** — a testable empirical assertion carrying evidence and/or
   counter-evidence ("X outperforms Y", "metric Z saturates").
4. **entity** — an **embodied** thing: a specific artifact with weights, data, or
   a repo (a model, dataset, benchmark-project, tool), or a real person / lab /
   organization. Singular, nominal identity.
5. **convention** — an **abstract normative practice**: *how the field conducts or
   reports evaluation* — a protocol, scoring scale, judging paradigm, or
   aggregation rule — owned by no single artifact and adopted across many.
6. **concept** (residual) — abstract knowledge that is none of the above: general
   theory, a definition or capability, or the **internal structure of an entity**
   (a benchmark's taxonomy, results table, pipeline, or a metric's mechanism).

### The spine: embodied vs. abstract

The hard boundary is **entity (embodied) vs. concept/convention (abstract)**:

- An **entity** is embodied — you obtain a *thing* (weights / data / repo) or it
  is a real person or organization. Among abstractions, a **convention** is a
  *practice* ("how the field evaluates") and a **concept** is *knowledge* ("what
  something is").
- **Citability and runnability are not criteria.** A judge model shipped inside
  another paper's release, with no standalone citation, is still an entity (it is
  embodied). A formula-metric is "runnable" but has no embodiment, so it is a
  concept.

### Tie-breakers

- **Paraphrase-identity test.** Rewrite *how it works* — is it still the same
  thing? Yes → **entity** (identity is its name; a named model survives a change
  to its internals). No → **concept/convention** (identity is its content; a named
  method stops being itself if you change what it means).
- **Entity vs. code-pattern.** Same artifact, different granularity: the whole
  named artifact is an **entity** (a reference node, no code body); a cited
  line-range of its source is a **code-pattern**.
- **Datasets.** The dataset-as-artifact is an **entity**; its schema/splits are a
  linked **concept**.
- **Metrics, split by embodiment.** A metric backed by weights or data (a trained
  reward/preference model) is an **entity**; a metric that is a formula or
  procedure (even if it invokes a separate model) is a **concept**, and the model
  it invokes is the entity.

The tell for entity-vs-convention is the verb: an entity **uses / reports /
applies** a convention. A benchmark-project (entity) *uses* a decomposition
paradigm (convention); a trained judge (entity) *applies* an aggregation rule
(convention). When X uses Y, X is the entity and Y the convention.

---

## Naming conventions

- File names: lowercase, hyphen-separated, ASCII only. No spaces, underscores, or unicode.
- One page per file. Never put two distinct pages in one file.
- A slug is unique across all page types. `concepts/foo` and `claims/foo` is a **duplicate-slug** lint error (because consumers cite by basename frequently).
- Avoid stop words in slugs (`the`, `a`, `of`) unless required for disambiguation.

---

## Frontmatter

YAML frontmatter is required on every page. Delimited by `---` lines at top of file.

### Common required fields (all types)

```yaml
---
title: string                    # human-readable display title
type: concept|convention|code-pattern|claim|source|entity
created: YYYY-MM-DD              # date page was created
last_verified: YYYY-MM-DD        # date a human or agent last confirmed accuracy
confidence: verified|likely|low|placeholder|refuted
---
```

### Common optional fields (all types)

```yaml
tags: [list, of, tags]           # free-form tags; lowercase, hyphenated
aliases: [other names]           # alternate display names; search will match these
draft: true                      # if true, build excludes the page
```

### Enum: `confidence`

| Value         | Meaning                                                            |
| ------------- | ------------------------------------------------------------------ |
| `verified`    | Cross-checked against multiple sources; trustworthy.               |
| `likely`      | Single solid source; high prior confidence.                        |
| `low`         | Best-effort synthesis; treat with care.                            |
| `placeholder` | Stub; structurally present but not yet filled. Excluded from build by default. |
| `refuted`     | Page asserted X; X has been disproved. Kept for traceability.      |

### Enum: `status` (claims only)

| Value       | Meaning                                                          |
| ----------- | ---------------------------------------------------------------- |
| `validated` | Strong consensus supports the claim.                             |
| `likely`    | Majority of evidence supports the claim.                         |
| `open`      | Genuine controversy or insufficient evidence either way.         |
| `refuted`   | Strong evidence against; kept for traceability.                  |

---

## Per-type frontmatter

### concept

```yaml
---
title: string
type: concept
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# optional
tags: [list]
aliases: [list]
---
```

Edge types allowed in frontmatter: **none** (only `references` via prose wikilinks).

### convention

```yaml
---
title: string
type: convention
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# optional
tags: [list]
aliases: [list]
field_examples: [list of example fields, repos, or papers exhibiting the convention]
---
```

Edge types allowed in frontmatter: **none**.

### code-pattern

```yaml
---
title: string
type: code-pattern
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# required for code-patterns
repo: "org/name"                 # github-style "org/name"
commit: "<full 40-char sha>"     # pinned commit
path: "src/foo/bar.py"           # path within repo
lines: "10-45"                   # line range; comma-separated for multiple
language: "python"               # programming language
# optional
tags: [list]
aliases: [list]
supersedes: [list of code-pattern slugs that this one obsoletes]
implements: [list of concept or convention slugs that this code realizes]
---
```

Edge types allowed in frontmatter: **`supersedes`**, **`implements`**.

The `lines:` field supports comma-separated ranges: `"10-45,60-72"`. Single line is `"10"`. Lines are 1-indexed and inclusive on both ends.

### claim

```yaml
---
title: string
type: claim
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# required for claims
status: validated|likely|open|refuted
evidence: [list of source-slug wikilink targets supporting the claim]
counter_evidence: [list supporting opposition]
# optional
tags: [list]
aliases: [list]
extends: [list of claim slugs this builds on]
contradicts: [list of claim slugs this disagrees with]
supersedes: [list of claim slugs this replaces]
---
```

Edge types allowed in frontmatter: **`extends`**, **`contradicts`**, **`supersedes`**.

`evidence` and `counter_evidence` may be empty lists, but the linter emits **claim-without-evidence** (error) if both are empty.

### source

```yaml
---
title: string
type: source
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# required for sources
source_type: paper|repo|doc|web|note
source_path: "raw/papers/<filename>"  # relative to repo root
content_hash: "sha256:<first-16-chars>"  # dedup hint for ingest
# optional but encouraged
url: string
authors: [list]
year: YYYY
venue: string                    # journal, conference, blog, etc.
tags: [list]
---
```

Edge types allowed in frontmatter: **none**.

Sources are exempt from the **orphan** lint warning — a source page may exist before anything cites it.

### entity

```yaml
---
title: string
type: entity
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
confidence: verified|likely|low|placeholder|refuted
# required for entities
entity_type: person|lab|project|tool|organization
# optional
url: string
tags: [list]
aliases: [list]
---
```

Edge types allowed in frontmatter: **none**.

---

## Wikilinks

Two complementary forms of cross-reference.

### Plain wikilinks (in prose)

Syntax: `[[<slug>]]` or `[[<slug>|display text]]`.

- Resolution: the `<slug>` matches the page path inside `wiki/` minus `.md`. Example: `[[concepts/optimization/sgd]]` resolves to `wiki/concepts/optimization/sgd.md`.
- Shorthand: a bare basename like `[[sgd]]` resolves if exactly one page in the wiki has that basename. If multiple, it is a **broken-wikilink** error and must be disambiguated.
- The build step emits these as rows in `.meta/links.tsv` with `edge_type=references`.

### Typed relationships (in frontmatter)

Lists in frontmatter — `extends:`, `contradicts:`, `supersedes:`, `implements:` — name target slugs the same way as prose wikilinks (no `[[ ]]` brackets in YAML).

```yaml
supersedes: [code-patterns/adam-classic, code-patterns/adam-with-warmup]
implements: [concepts/optimization/momentum]
```

The build step emits these as rows in `.meta/links.tsv` with the declared edge type. If a target appears in both prose and a typed frontmatter list, the typed row wins (frontmatter has higher precedence than prose).

### Edge-type vocabulary (fixed in v1)

| Edge type     | Meaning                                                              |
| ------------- | -------------------------------------------------------------------- |
| `references`  | Default. Page A mentions or relates to page B. Emitted from prose.   |
| `extends`     | Page A builds on the foundation page B established.                  |
| `contradicts` | Page A asserts something incompatible with page B.                   |
| `supersedes`  | Page A replaces page B; B is obsolete.                               |
| `implements`  | Page A is a realization of the concept/convention page B.            |

Adding a sixth edge type requires a `schema_version` bump, a new lint rule, and explicit discussion. Resist this in v1.

### Allowed edge types per page type

| Page type     | References (prose) | extends | contradicts | supersedes | implements |
| ------------- | ------------------ | ------- | ----------- | ---------- | ---------- |
| concept       | yes                | no      | no          | no         | no         |
| convention    | yes                | no      | no          | no         | no         |
| code-pattern  | yes                | no      | no          | yes        | yes        |
| claim         | yes                | yes     | yes         | yes        | no         |
| source        | yes                | no      | no          | no         | no         |
| entity        | yes                | no      | no          | no         | no         |

Declaring a disallowed edge type is a **disallowed-edge-type** lint error.

---

## Body conventions

- **Narrative prose stays concise; structured content is captured in full.** A page's *prose* should be brief — agents read pages whole. But *structured, enumerable* content (taxonomies, workflows/pipelines, code structures with their key workflows and design ideas, metrics and tabular data, algorithm steps) must be captured **completely and faithfully**: reconcile counts/totals and cross-check a source's table against its appendix/figures. If a faithful reference page would run long (≫300 lines), **split it into linked pages** — never drop content to hit a length target.
- **Link densely — the graph is a product, not decoration.** Use `[[wikilinks]]` liberally in prose; every page should link out *and* be linked to. Create `concepts/`/`entities/` hub pages for recurring metrics, datasets, tools, and methods so multiple sources share nodes.
- For `code-patterns/` pages, the body should briefly describe what the pattern does, when to use it, and known gotchas. The actual code excerpt is **not** embedded — the build step copies it to `wiki/snippets/<slug>.txt` from the cited `raw/repos/` path.
- For `claims/` pages, the body lays out the assertion, the supporting evidence (citing the `evidence:` sources by wikilink), and the opposition.
- For `sources/` pages, the body is the agent's read of what the source contributes — key claims, gaps, suspect parts. Keep it to one screen of *prose*; push exhaustive structured detail (taxonomies, tables, pipelines) into dedicated `concepts/` (or other typed) pages and link to them.

### Forward-linking with placeholder stubs

A `[[wikilink]]` to a page that does not exist is a hard `broken-wikilink`
error, which would otherwise block forward references to concepts you have not
written yet. To link forward, create the target as a **placeholder stub**: a
`confidence: placeholder` page (tagged `stub`) carrying a one-line *What it is*
gloss and a *Linked from* context line. Stubs are excluded from the build,
surface as a worklist under `lint --report`'s `## Placeholder stubs / wanted
pages`, and are filled later by ingest/explorer. Create them with
`ingest_helpers.create_placeholder_stub()` — it is restricted to `concepts/` and
`entities/` and requires the gloss + linked-from context, so a stub is always
self-describing. Do **not** stub out-of-scope references (e.g. model-catalog
names); leave those as plain text.

---

## Index artifacts

`.forge/lib/index.py` produces the wiki's derived index: two TSV files in
`wiki/.meta/` (consumed by the `bin/wiki-*` read scripts) and `wiki/index.md`
(the human/agent catalog page). It is invoked on demand in the curator
workspace (by `ingest` after a run and by `lint --fix`) and by `build.py` when
assembling a bundle. The curator-side index covers every page; the bundle-side
index covers only the pages that ship.

### `pages.tsv`

Tab-separated, one row per page. Columns:

```
path<TAB>title<TAB>type<TAB>tags<TAB>last_verified<TAB>confidence
```

`path` is the slug (no `wiki/` prefix, no `.md` suffix). `tags` is comma-separated.

### `links.tsv`

Tab-separated, one row per directed edge. Columns:

```
from<TAB>to<TAB>edge_type
```

`from` and `to` are slugs. `edge_type` is one of the five vocabulary terms.

Both files are regenerated by `index.py`; they are derived artifacts and are
never hand-edited. In the curator workspace `wiki/.meta/` is gitignored.
