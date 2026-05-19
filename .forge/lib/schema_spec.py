"""schema_spec.py — machine-readable encoding of schema.md.

The source of truth is `schema.md` at the workspace root. This file is consumed by
`lint.py` and `build.sh` (via lint). Keep both in sync; the lint suite includes a
schema-version sanity check.
"""

SCHEMA_VERSION = 1

PAGE_TYPES = ["concept", "convention", "code-pattern", "claim", "source", "entity"]

# directory under wiki/ for each page type
TYPE_DIRS = {
    "concept": "concepts",
    "convention": "conventions",
    "code-pattern": "code-patterns",
    "claim": "claims",
    "source": "sources",
    "entity": "entities",
}
DIR_TYPES = {v: k for k, v in TYPE_DIRS.items()}

# top-level files under wiki/ that are not "pages" in the page-type sense
META_FILES = {"manifest", "index", "log", "out_of_scope"}

# enum values
CONFIDENCE = {"verified", "likely", "low", "placeholder", "refuted"}
CLAIM_STATUS = {"validated", "likely", "open", "refuted"}
ENTITY_TYPE = {"person", "lab", "project", "tool", "organization"}
SOURCE_TYPE = {"paper", "repo", "doc", "web", "note"}

# edge-type vocabulary — fixed in v1
EDGE_TYPES = {"references", "extends", "contradicts", "supersedes", "implements"}
TYPED_EDGE_FIELDS = ("extends", "contradicts", "supersedes", "implements")

# required frontmatter — common across all page types
COMMON_REQUIRED = ["title", "type", "created", "last_verified", "confidence"]

# additional required fields per page type
REQUIRED = {
    "concept": [],
    "convention": [],
    "code-pattern": ["repo", "commit", "path", "lines", "language"],
    "claim": ["status", "evidence", "counter_evidence"],
    "source": ["source_type", "source_path", "content_hash"],
    "entity": ["entity_type"],
}

# typed edges each page type may declare in its frontmatter
ALLOWED_EDGE_TYPES = {
    "concept": set(),
    "convention": set(),
    "code-pattern": {"supersedes", "implements"},
    "claim": {"extends", "contradicts", "supersedes"},
    "source": set(),
    "entity": set(),
}

# page types exempt from the orphan warning (e.g., sources may exist before anything cites them)
ORPHAN_EXEMPT = {"source"}

DATE_FMT = "%Y-%m-%d"

# lint thresholds (default; can be overridden via CLI)
STALE_DAYS = 180
PLACEHOLDER_ROT_DAYS = 30
