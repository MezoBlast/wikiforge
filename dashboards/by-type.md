# By type

Counts, recent activity, and longest-untouched pages per type.

## Counts

```dataview
TABLE WITHOUT ID
    type AS "Type",
    length(rows) AS "Count"
FROM "wiki"
WHERE type AND type != "index"
GROUP BY type
SORT type ASC
```

## Added in the last 14 days

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    created
FROM "wiki"
WHERE created AND (date(today) - date(created)).days <= 14
SORT created DESC
```

## Longest untouched (top 20)

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    last_verified,
    (date(today) - date(last_verified)).days AS "days since"
FROM "wiki"
WHERE last_verified AND type
SORT (date(today) - date(last_verified)).days DESC
LIMIT 20
```
