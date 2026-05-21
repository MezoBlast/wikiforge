#!/usr/bin/env python3
"""lint.py — mechanical health checks for a wikiforge wiki.

Modes:
  --report   print all issues, exit 0 (default)
  --strict   same output, exit non-zero on any error
  --fix      conservative auto-fixes (rebuild index.md). Never deletes pages.
"""
import argparse
import datetime
import sys
from pathlib import Path

# allow `import schema_spec`, etc. when invoked as `python3 .forge/lib/lint.py`
sys.path.insert(0, str(Path(__file__).parent))

import schema_spec as S
import frontmatter as FM
import wikilinks as WL
import index

ERROR = "error"
WARNING = "warning"


class Issue:
    __slots__ = ("severity", "code", "page", "message")

    def __init__(self, severity, code, page, message):
        self.severity = severity
        self.code = code
        self.page = page
        self.message = message

    def fmt(self):
        return f"[{self.severity:<7}] {self.code:<32} {self.page}: {self.message}"


def parse_date(s):
    if isinstance(s, datetime.date):
        return s
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.datetime.strptime(s, S.DATE_FMT).date()
    except ValueError:
        return None


def detect_type_from_slug(slug):
    first = slug.split("/", 1)[0]
    return S.DIR_TYPES.get(first)


def discover_pages(wiki_dir):
    """Yield (slug, path, fm_or_error, body_or_None) for every .md under wiki/."""
    out = []
    for md in sorted(wiki_dir.rglob("*.md")):
        if ".meta" in md.parts:
            continue
        rel = md.relative_to(wiki_dir).with_suffix("")
        slug = rel.as_posix()
        if slug in S.META_FILES:
            try:
                text = md.read_text(encoding="utf-8")
            except OSError as e:
                out.append((slug, md, e, None))
                continue
            out.append((slug, md, None, text))
            continue
        try:
            fm, body = FM.load(md)
            out.append((slug, md, fm, body))
        except FM.FrontmatterError as e:
            out.append((slug, md, e, None))
    return out


def build_indices(pages):
    """Return (valid_slugs, basename_index, fm_map).

    `valid_slugs` and `basename_index` include meta files so that prose can link
    to them (e.g. `[[index]]`). `fm_map` excludes meta files since they have no
    validated frontmatter contract.
    """
    valid_slugs = set()
    basename_index = {}
    fm_map = {}
    for slug, _, fm, _ in pages:
        valid_slugs.add(slug)
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)
        if slug not in S.META_FILES and isinstance(fm, dict):
            fm_map[slug] = fm
    return valid_slugs, basename_index, fm_map


def check_frontmatter(slug, page_type, fm, issues):
    """Per-page frontmatter validation. Mutates `issues`."""
    # declared type matches directory
    declared_type = fm.get("type")
    if declared_type != page_type:
        issues.append(Issue(ERROR, "frontmatter-schema", slug,
            f"declared type {declared_type!r} does not match directory ({page_type!r})"))

    # common required fields
    for field in S.COMMON_REQUIRED:
        v = fm.get(field)
        if v is None or v == "":
            issues.append(Issue(ERROR, "missing-required-frontmatter", slug,
                f"missing required field {field!r}"))

    # per-type required fields
    for field in S.REQUIRED.get(page_type, []):
        if field not in fm:
            issues.append(Issue(ERROR, "missing-required-frontmatter", slug,
                f"missing required field for {page_type}: {field!r}"))

    # enum checks
    conf = fm.get("confidence")
    if conf is not None and conf not in S.CONFIDENCE:
        issues.append(Issue(ERROR, "frontmatter-schema", slug,
            f"invalid confidence {conf!r}; must be one of {sorted(S.CONFIDENCE)}"))
    if page_type == "claim":
        st = fm.get("status")
        if st is not None and st not in S.CLAIM_STATUS:
            issues.append(Issue(ERROR, "frontmatter-schema", slug,
                f"invalid status {st!r}; must be one of {sorted(S.CLAIM_STATUS)}"))
    if page_type == "source":
        st = fm.get("source_type")
        if st is not None and st not in S.SOURCE_TYPE:
            issues.append(Issue(ERROR, "frontmatter-schema", slug,
                f"invalid source_type {st!r}; must be one of {sorted(S.SOURCE_TYPE)}"))
    if page_type == "entity":
        et = fm.get("entity_type")
        if et is not None and et not in S.ENTITY_TYPE:
            issues.append(Issue(ERROR, "frontmatter-schema", slug,
                f"invalid entity_type {et!r}; must be one of {sorted(S.ENTITY_TYPE)}"))

    # claim-without-evidence
    if page_type == "claim":
        ev = fm.get("evidence") or []
        cev = fm.get("counter_evidence") or []
        if not ev and not cev:
            issues.append(Issue(ERROR, "claim-without-evidence", slug,
                "both 'evidence' and 'counter_evidence' are empty"))


def check_code_pattern_excerpt(slug, fm, raw_dir, issues):
    repo = fm.get("repo"); commit = fm.get("commit")
    path = fm.get("path"); lines = fm.get("lines")
    if not (repo and commit and path and lines):
        issues.append(Issue(ERROR, "code-pattern-missing-provenance", slug,
            "must declare repo, commit, path, lines"))
        return
    src = raw_dir / "repos" / f"{repo}@{commit}" / path
    if not src.exists():
        issues.append(Issue(ERROR, "excerpt-missing", slug,
            f"raw/repos/{repo}@{commit}/{path} does not exist"))


def check_stale_index(wiki_dir, issues):
    """Warn if wiki/.meta/pages.tsv is missing or older than the newest page."""
    meta = wiki_dir / ".meta" / "pages.tsv"
    newest = 0.0
    for md in wiki_dir.rglob("*.md"):
        if ".meta" in md.parts:
            continue
        newest = max(newest, md.stat().st_mtime)
    if not meta.exists():
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            "wiki/.meta/ index missing — run python3 .forge/lib/lint.py --fix"))
        return
    if meta.stat().st_mtime < newest:
        issues.append(Issue(WARNING, "stale-index", ".meta/pages.tsv",
            "index older than newest wiki page — run python3 .forge/lib/lint.py --fix"))


def lint(wiki_dir, raw_dir, stale_days, rot_days, today):
    issues = []
    pages = discover_pages(wiki_dir)
    valid_slugs, basename_index, fm_map = build_indices(pages)
    check_stale_index(wiki_dir, issues)

    # duplicate-slug across types
    for bn, slugs in basename_index.items():
        if len(slugs) <= 1:
            continue
        top_dirs = {s.split("/", 1)[0] for s in slugs}
        if len(top_dirs) > 1:
            for s in slugs:
                others = sorted(x for x in slugs if x != s)
                issues.append(Issue(ERROR, "duplicate-slug", s,
                    f"basename {bn!r} duplicates: {others}"))

    incoming = {s: 0 for s in valid_slugs}

    def record_link(from_slug, target, edge):
        """Resolve link; record incoming or emit broken-wikilink."""
        target = WL.normalize_target(target)
        resolved = WL.resolve(target, valid_slugs, basename_index)
        if resolved is None:
            matches = basename_index.get(target, ())
            if len(matches) > 1:
                issues.append(Issue(ERROR, "broken-wikilink", from_slug,
                    f"ambiguous [[{target}]] matches {sorted(matches)}"))
            else:
                issues.append(Issue(ERROR, "broken-wikilink", from_slug,
                    f"unresolved [[{target}]]"))
            return
        incoming[resolved] = incoming.get(resolved, 0) + 1

    for slug, md, fm, body in pages:
        # meta files: only scan body for wikilinks
        if slug in S.META_FILES:
            if isinstance(body, str):
                for raw in WL.extract_prose_links(body):
                    record_link(slug, raw, "references")
            continue

        # frontmatter parse failure → single error, no further checks
        if isinstance(fm, Exception):
            issues.append(Issue(ERROR, "missing-required-frontmatter", slug, str(fm)))
            continue

        page_type = detect_type_from_slug(slug)
        if page_type is None:
            issues.append(Issue(ERROR, "frontmatter-schema", slug,
                "page lives in an unknown directory for its type"))
            continue

        check_frontmatter(slug, page_type, fm, issues)
        if page_type == "code-pattern":
            check_code_pattern_excerpt(slug, fm, raw_dir, issues)

        # typed frontmatter edges
        allowed = S.ALLOWED_EDGE_TYPES.get(page_type, set())
        for edge, target in WL.extract_frontmatter_edges(fm):
            if edge not in allowed:
                issues.append(Issue(ERROR, "disallowed-edge-type", slug,
                    f"page type {page_type!r} may not declare {edge!r}"))
            record_link(slug, target, edge)

        # stale
        lv = parse_date(fm.get("last_verified"))
        if lv and (today - lv).days > stale_days:
            issues.append(Issue(WARNING, "stale", slug,
                f"last_verified {lv.isoformat()} > {stale_days} days ago"))

        # placeholder-rotting
        if fm.get("confidence") == "placeholder":
            cdate = parse_date(fm.get("created"))
            if cdate and (today - cdate).days > rot_days:
                issues.append(Issue(WARNING, "placeholder-rotting", slug,
                    f"placeholder for {(today - cdate).days} days (>{rot_days})"))

        # prose wikilinks
        if isinstance(body, str):
            for raw in WL.extract_prose_links(body):
                record_link(slug, raw, "references")

    # orphan check
    for slug, _, fm, _ in pages:
        if slug in S.META_FILES or not isinstance(fm, dict):
            continue
        pt = detect_type_from_slug(slug)
        if pt in S.ORPHAN_EXEMPT:
            continue
        if incoming.get(slug, 0) == 0:
            issues.append(Issue(WARNING, "orphan", slug, "no incoming links"))

    # cross-page checks
    for slug, fm in fm_map.items():
        pt = detect_type_from_slug(slug)

        # superseded-not-stale
        for target in fm.get("supersedes") or []:
            target = WL.normalize_target(target) if isinstance(target, str) else target
            t_fm = fm_map.get(target)
            if not t_fm:
                continue  # broken-wikilink already flagged
            t_lv = parse_date(t_fm.get("last_verified"))
            t_conf = t_fm.get("confidence")
            if t_lv and (today - t_lv).days < stale_days and t_conf not in ("refuted", "low"):
                issues.append(Issue(WARNING, "superseded-not-stale", target,
                    f"superseded by {slug} but last_verified is recent and confidence is {t_conf!r}"))

        # contradicts-asymmetric
        for target in fm.get("contradicts") or []:
            target = WL.normalize_target(target) if isinstance(target, str) else target
            t_fm = fm_map.get(target)
            if not t_fm:
                continue
            backrefs = set()
            for f in S.TYPED_EDGE_FIELDS:
                for x in (t_fm.get(f) or []):
                    if isinstance(x, str):
                        backrefs.add(WL.normalize_target(x))
            if slug not in backrefs:
                issues.append(Issue(WARNING, "contradicts-asymmetric", slug,
                    f"contradicts {target!r} but {target!r} has no back-reference"))

        # claim-supports-without-evidence
        if pt == "claim" and (fm.get("extends") or []) and not (fm.get("evidence") or []):
            issues.append(Issue(WARNING, "claim-supports-without-evidence", slug,
                "claim extends another but has empty 'evidence' list"))

    return issues


def fix(wiki_dir, today):
    """Conservative auto-fix: rebuild index.md and wiki/.meta/ from current
    pages, via index.py. Never deletes or mutates pages."""
    pages = list(index.load_pages(wiki_dir))
    index.write_index_md(wiki_dir, pages, today)
    print(f"rebuilt {wiki_dir / 'index.md'}")
    index.write_meta(wiki_dir / ".meta", pages)
    print(f"rebuilt {wiki_dir / '.meta'}")


def main():
    p = argparse.ArgumentParser(prog="lint", description="wikiforge wiki linter")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--report", action="store_true",
                   help="print issues, exit 0 (default)")
    g.add_argument("--strict", action="store_true",
                   help="print issues, exit non-zero on any error")
    g.add_argument("--fix", action="store_true",
                   help="conservatively rebuild index.md and wiki/.meta/")
    p.add_argument("--wiki", default="wiki", help="path to wiki dir (default: wiki)")
    p.add_argument("--raw", default="raw", help="path to raw dir (default: raw)")
    p.add_argument("--stale-days", type=int, default=S.STALE_DAYS)
    p.add_argument("--rot-days", type=int, default=S.PLACEHOLDER_ROT_DAYS)
    args = p.parse_args()

    wiki_dir = Path(args.wiki).resolve()
    raw_dir = Path(args.raw).resolve()
    if not wiki_dir.is_dir():
        print(f"lint: wiki dir not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today()

    if args.fix:
        fix(wiki_dir, today)
        return

    issues = lint(wiki_dir, raw_dir, args.stale_days, args.rot_days, today)
    issues.sort(key=lambda i: (0 if i.severity == ERROR else 1, i.code, i.page))
    for i in issues:
        print(i.fmt())
    sys.stdout.flush()
    n_err = sum(1 for i in issues if i.severity == ERROR)
    n_warn = len(issues) - n_err
    print(f"\n{n_err} error(s), {n_warn} warning(s)", file=sys.stderr)

    if args.strict and n_err > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
