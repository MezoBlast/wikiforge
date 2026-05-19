# Orphans

Pages with no incoming links. Sources (`wiki/sources/`) are excluded — a source may exist before anything cites it. Meta files (`manifest`, `index`, `log`, `out_of_scope`) are also excluded.

If a page is here for long, ask: should something link to it? Should it be merged into a parent page? Or should it be in `out_of_scope.md`?

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    confidence,
    last_verified
FROM "wiki"
WHERE type AND type != "source" AND length(file.inlinks) = 0
SORT type ASC, file.name ASC
```
