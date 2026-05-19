# Stale pages

Pages whose `last_verified` is more than 180 days old. The lint rule matches this threshold.

A stale page is not necessarily wrong — it just hasn't been re-checked. Re-verifying might be as simple as re-reading the cited source and bumping the date, or it might surface a real correction.

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    last_verified,
    (date(today) - date(last_verified)).days AS "days since",
    confidence
FROM "wiki"
WHERE last_verified AND (date(today) - date(last_verified)).days > 180
SORT (date(today) - date(last_verified)).days DESC
```
