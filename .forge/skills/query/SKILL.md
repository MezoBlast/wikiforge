---
name: wikiforge-query
description: Answer a question from wiki content, citing pages by [[wikilink]]. Reads the wiki/.meta/ index; never writes wiki pages. Records unanswerable questions to .forge/feedback.md.
---

# query — wiki → answer

You have been asked a question. Answer it **from the wiki**, citing the pages
you used.

## Principle: answer from the wiki, not from memory

The point of this skill is a *grounded* answer — built from wiki pages whose
provenance you can name — rather than parametric recall mixed with
hallucination. The wiki is the input, not a hint. If a statement in your answer
is not supported by a wiki page you can cite, it does not belong in a `query`
answer. A question the wiki cannot support is not something you improvise around;
it is a gap you record (step 6).

`query` is **read-only over the wiki**. It never creates or edits wiki pages and
never writes the index. Its one and only write is an append to
`.forge/feedback.md`.

## Workflow

### 1. Orient

The `bin/wiki-*` scripts read a prebuilt index at `wiki/.meta/`. Read the
manifest:

```sh
bin/wiki-manifest
```

If a `bin/wiki-*` command reports `no wiki/.meta/...`, or a recent `lint` run
reported a `stale-index` warning, the index is missing or stale. **Stop** — do
not write the index yourself. Ask for it to be refreshed:

```sh
python3 .forge/lib/lint.py --fix      # rebuilds index.md and wiki/.meta/
```

Then re-run `bin/wiki-manifest`. Skim the top topics and `wiki/out_of_scope.md`.
Is the question in scope? If it falls under an explicit exclusion, say so and
stop — that is a correct answer, not a gap.

### 2. Search

```sh
bin/wiki-search <terms>
bin/wiki-search --type claim <terms>     # narrow to one page type
```

`--type` accepts any of the six page types: `concept`, `convention`,
`code-pattern`, `claim`, `source`, `entity`. Results rank title > tag > body
matches; `--n N` caps the count (default 10).

To browse rather than search:

```sh
bin/wiki-list --type concept             # every concept page
bin/wiki-list --tag optimization         # every page carrying a tag
```

### 3. Read

For each candidate (top 3–5):

```sh
bin/wiki-read <slug>
```

Pay attention to:
- The frontmatter `confidence:` field — `verified` and `likely` are strong;
  `low` and `placeholder` are weak; `refuted` means the page documents
  something that has been disproved.
- The appended **Backlinks** block — typed backlinks (`contradicts:`,
  `supersedes:`) are load-bearing context.
- For `claims/` pages, the `evidence:` and `counter_evidence:` lists name
  `sources/` pages you can also read.

To inspect one relationship sharply:

```sh
bin/wiki-backlinks --type contradicts <slug>   # what disputes this page
bin/wiki-backlinks --type supersedes <slug>    # what replaces it
```

### 4. Follow & corroborate

Follow `[[wikilinks]]` in prose when they are load-bearing for the answer — do
not follow exhaustively; stop when you have enough. Prefer a **corroborated**
answer: where two or more pages (or a page plus its `evidence:` sources) agree,
say so. Where the answer rests on a single page, say *that* too — single-source
is not wrong, but the reader deserves to know.

### 5. Synthesize

Write the answer. **Cite every claim** with the source page's wikilink
(`[[concepts/foo]]`, `[[claims/bar]]`). Quote a `code-patterns/` page when
implementation matters, and point the reader at `wiki/snippets/<slug>.txt` for
the code itself. If the most relevant page is `confidence: low` or
`placeholder`, the answer must say so — never launder a weak page into a
confident answer.

### 6. Record the gap

If the wiki could not fully answer the question, append an entry to
`.forge/feedback.md` so the `explorer` and `ingest` skills can close the gap. If
the file does not exist, create it with this header line first:

```
# .forge/feedback.md — append-only curator feedback log
```

Then append one entry. Two severities:

**`hard`** — no wiki page covers the question, or every relevant page is out of
scope:

```
## [2026-05-20T14:03:00Z] query-gap | severity: hard
Q: How does X handle Y?
No page covers this. Suggest ingesting: <topic or named source>.
```

**`weak`** — you answered, but only from `low`/`placeholder` pages:

```
## [2026-05-20T14:07:00Z] query-gap | severity: weak
Q: What is Z?
Answered from [[concepts/z]] (confidence: low). Needs a corroborating source.
```

Use a UTC ISO-8601 timestamp. One entry per unanswerable or weakly-answered
question. The file is **append-only** — never edit or delete prior entries. The
`explorer` skill harvests it; a `hard` gap scores as high as real consumer
feedback.

## Worked example — an answerable question

> *"What optimizer does the wiki recommend for sparse gradients?"*

```sh
bin/wiki-manifest                        # in scope: optimization is a top topic
bin/wiki-search sparse gradient
#   [1] concepts/optimization/adagrad (title)
#   [3] concepts/optimization/sgd (body)
bin/wiki-read concepts/optimization/adagrad
#   confidence: verified; Backlinks shows [[claims/adagrad-sparse-strong]] (extends)
bin/wiki-read claims/adagrad-sparse-strong
#   confidence: likely; evidence: [[sources/duchi-2011]]
```

Answer: *"For sparse gradients the wiki recommends AdaGrad
([[concepts/optimization/adagrad]]) — its per-parameter learning rates adapt to
feature frequency. [[claims/adagrad-sparse-strong]] supports this, citing
[[sources/duchi-2011]]. (One primary source — `likely`, not `verified`.)"*

No `.forge/feedback.md` entry: the wiki answered.

## Worked example — a hard gap

> *"What's the wiki's take on the Lion optimizer?"*

```sh
bin/wiki-search lion optimizer           # no results
bin/wiki-search --type claim lion        # no results
```

The wiki has nothing. Answer honestly: *"The wiki has no page on the Lion
optimizer. I won't answer from memory — I've recorded the gap."* Then append to
`.forge/feedback.md`:

```
## [2026-05-20T15:20:00Z] query-gap | severity: hard
Q: What is the wiki's assessment of the Lion optimizer?
No page covers this. Suggest ingesting: the Lion paper (Chen et al. 2023,
"Symbolic Discovery of Optimization Algorithms").
```

## What query is **not**

- Not a paraphrasing service. If a page says it well, quote it (with a
  wikilink) rather than rewriting.
- Not a research session. If answering needs sources the wiki lacks, record the
  gap (step 6) — do not fetch. That is the `explorer` skill's job.
- Not a place to lower the bar. A `low`-confidence answer is reported as a
  `low`-confidence answer.
- Not a writer of wiki pages or the index. The only file `query` writes is
  `.forge/feedback.md`.
