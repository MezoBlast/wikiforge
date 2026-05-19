---
name: wikiforge-query
description: Answer a question from wiki content, citing pages by [[wikilink]]. Curator-side analogue of the bundle's bin/wiki-search + bin/wiki-read pipeline.
---

# query — wiki → answer

You have been asked a question. Your job is to answer it from the wiki, citing the pages you used. **Do not hallucinate — if the wiki doesn't have the answer, say so explicitly and (optionally) note what would need to be ingested to cover it.**

## Workflow

1. **Orient.** Run `bin/wiki-manifest`. Skim the top topics and out-of-scope list. Is the question in scope?

2. **Search.** Use `bin/wiki-search <terms>` to find candidate pages. For specific questions, narrow with `--type concept|claim|code-pattern`. The output ranks title > tag > body matches.

3. **Read.** For each candidate (top 3–5), run `bin/wiki-read <slug>`. Pay attention to:
   - The frontmatter `confidence:` field — `low` and `placeholder` are weak.
   - The backlinks block — typed backlinks (`contradicts:`, `supersedes:`) are load-bearing context.
   - The page body's evidence trail (for `claims/`, the `evidence:` and `counter_evidence:` lists are sources you can also read).

4. **Follow.** If a page links to others ([[wikilinks]] in prose), read those when they're load-bearing for the answer. Don't follow exhaustively — stop when you have enough.

5. **Synthesize.** Write the answer. Cite every claim with the source page's wikilink (`[[concepts/foo]]`, `[[claims/bar]]`). Quote a `code-patterns/` page when implementation matters; refer the reader to `wiki/snippets/<slug>.txt` for the code.

6. **Caveats.** Append a short "what's weak" note if applicable:
   - "Most evidence comes from one source ([[sources/x]]); a second source would strengthen this."
   - "[[claims/y]] supersedes a prior page on this topic — the older view in the wiki is intentionally retained for traceability."
   - "Out of scope per [[out_of_scope]]: for recent leaderboard scores, fall back to live retrieval."

## What query is **not**

- Not a paraphrasing service. If the wiki page says it well, quote it (with a wikilink) rather than rewriting.
- Not a research session. If the question requires reading sources the wiki doesn't yet cover, say so — that's a signal for the explorer skill to fill the gap.
- Not a place to silently lower the bar. If `confidence:` on the most relevant page is `low`, the answer should reflect that.
