# log.md — wiki operation log

Append-only record of curator operations against the wiki. One entry per operation, most recent at the bottom.

Format:

```
## [YYYY-MM-DD] <skill> | <target>

Optional one-sentence note. Wikilinks to affected pages encouraged.
```

Skills that write here: `ingest`, `lint --fix`, `explorer` (when staging), human (manual edits).

---

## [{{DATE}}] init | wikiforge-{{NAME}}

Workspace created.
