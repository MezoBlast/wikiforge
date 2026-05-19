# Low-confidence and placeholder pages

Pages with `confidence: low` or `confidence: placeholder`. Group by type to make triage easier.

`placeholder` pages older than 30 days also trigger the `placeholder-rotting` lint warning.

## low

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    last_verified
FROM "wiki"
WHERE confidence = "low"
SORT type ASC, file.name ASC
```

## placeholder

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    created,
    (date(today) - date(created)).days AS "days as placeholder"
FROM "wiki"
WHERE confidence = "placeholder"
SORT (date(today) - date(created)).days DESC
```

## refuted (kept for traceability)

```dataview
TABLE WITHOUT ID
    file.link AS Page,
    type,
    last_verified
FROM "wiki"
WHERE confidence = "refuted"
SORT type ASC, file.name ASC
```
