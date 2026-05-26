#!/usr/bin/env python3
"""index.py — build the wiki index: wiki/.meta/ (pages.tsv, links.tsv) and index.md.

wiki/.meta/ is a derived index of the wiki, consumed by the bin/wiki-* read
scripts. It is a wiki artifact: maintained by whoever mutates the wiki (ingest
after a run, lint --fix on demand) and produced into the bundle by build.py.

Run as a CLI to regenerate the curator workspace index:

    python3 .forge/lib/index.py [--wiki wiki]

The CLI indexes every page, including drafts and placeholders — the curator
searches work in progress. build.py imports these functions and passes its own
filtered (build-eligible) page set.
"""
import argparse
import datetime
import sys
from pathlib import Path

# allow `import schema_spec`, etc. when invoked as `python3 .forge/lib/index.py`
sys.path.insert(0, str(Path(__file__).parent))

import schema_spec as S
import frontmatter as FM
import wikilinks as WL


def load_pages(wiki_dir):
    """Yield (slug, page_type, fm, body) for every page under wiki/.

    For meta files (manifest, index, log, out_of_scope), page_type is None and
    fm is None. Pages with unparseable frontmatter are skipped (lint flags them).
    """
    for md in sorted(wiki_dir.rglob("*.md")):
        if ".meta" in md.parts:
            continue
        rel = md.relative_to(wiki_dir).with_suffix("")
        slug = rel.as_posix()
        if slug in S.META_FILES:
            yield slug, None, None, md.read_text(encoding="utf-8")
            continue
        try:
            fm, body = FM.load(md)
        except FM.FrontmatterError:
            continue  # lint already flagged it
        page_type = S.DIR_TYPES.get(slug.split("/", 1)[0])
        yield slug, page_type, fm, body


def write_pages_tsv(meta_dir, pages):
    """Write meta_dir/pages.tsv. meta_dir must already exist."""
    rows = ["path\ttitle\ttype\ttags\tlast_verified\tconfidence"]
    for slug, pt, fm, _ in pages:
        if pt is None:
            continue
        title = str(fm.get("title", slug)).replace("\t", " ").replace("\n", " ")
        tags = ",".join(str(t) for t in (fm.get("tags") or []))
        lv = fm.get("last_verified")
        lv = lv.isoformat() if isinstance(lv, datetime.date) else (lv or "")
        conf = fm.get("confidence", "")
        rows.append(f"{slug}\t{title}\t{pt}\t{tags}\t{lv}\t{conf}")
    (meta_dir / "pages.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_links_tsv(meta_dir, pages, kept_slugs):
    """Write meta_dir/links.tsv. Frontmatter typed edges win over prose for the
    same (from, to) pair. meta_dir must already exist."""
    basename_index = {}
    for slug in kept_slugs:
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)

    def resolve(target):
        return WL.resolve(WL.normalize_target(target), kept_slugs, basename_index)

    typed = {}        # (from, to) -> edge_type
    prose = set()     # (from, to) for references

    for slug, pt, fm, body in pages:
        if pt is None:
            continue  # meta files (manifest, index, log, out_of_scope) — skip
        if isinstance(fm, dict):
            for edge, target in WL.extract_frontmatter_edges(fm):
                if edge not in S.EDGE_TYPES:
                    raise SystemExit(
                        f"unknown-edge-type: {slug} declares {edge!r}; "
                        f"vocabulary is {sorted(S.EDGE_TYPES)}"
                    )
                resolved = resolve(target)
                if not resolved:
                    raise RuntimeError(
                        f"internal: unresolved target {target!r} from {slug!r} "
                        f"(frontmatter:{edge}) reached write_links_tsv; "
                        f"validate_no_dangling_refs should have caught this"
                    )
                typed[(slug, resolved)] = edge
        if isinstance(body, str):
            for raw in WL.extract_prose_links(body):
                resolved = resolve(raw)
                if not resolved:
                    raise RuntimeError(
                        f"internal: unresolved target {raw!r} from {slug!r} "
                        f"(body) reached write_links_tsv; "
                        f"validate_no_dangling_refs should have caught this"
                    )
                prose.add((slug, resolved))

    rows = ["from\tto\tedge_type"]
    seen = set()
    for (f, t), edge in sorted(typed.items()):
        rows.append(f"{f}\t{t}\t{edge}")
        seen.add((f, t))
    for (f, t) in sorted(prose):
        if (f, t) in seen:
            continue
        rows.append(f"{f}\t{t}\treferences")
    (meta_dir / "links.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_meta(meta_dir, pages):
    """Create meta_dir and write both pages.tsv and links.tsv from `pages`
    (an iterable of (slug, page_type, fm, body) tuples, as load_pages yields)."""
    pages = list(pages)
    kept_slugs = {slug for slug, pt, _, _ in pages if pt is not None}
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_pages_tsv(meta_dir, pages)
    write_links_tsv(meta_dir, pages, kept_slugs)


def write_index_md(wiki_dir, pages, today):
    """Render wiki_dir/index.md: a catalog of all pages grouped by type.

    `pages` is an iterable of (slug, page_type, fm, body) tuples, as load_pages
    yields. Meta files (page_type None) are skipped.
    """
    by_type = {}
    for slug, page_type, fm, _ in pages:
        if page_type is None or not isinstance(fm, dict):
            continue
        by_type.setdefault(page_type, []).append((slug, fm.get("title", slug)))
    lines = [
        "---",
        "title: index",
        "type: index",
        f"created: {today.isoformat()}",
        f"last_verified: {today.isoformat()}",
        "---",
        "",
        "# Index",
        "",
        "Catalog of all pages, grouped by type. Rebuilt by `.forge/lib/index.py`.",
        "",
    ]
    for pt in S.PAGE_TYPES:
        lines.append(f"## {S.TYPE_DIRS[pt]}")
        lines.append("")
        entries = sorted(by_type.get(pt, []))
        if not entries:
            lines.append("_(none)_")
        else:
            for slug, title in entries:
                lines.append(f"- [[{slug}]] — {title}")
        lines.append("")
    (wiki_dir / "index.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(prog="index",
                                description="regenerate the wiki index")
    p.add_argument("--wiki", default="wiki", help="path to wiki dir (default: wiki)")
    args = p.parse_args()
    wiki_dir = Path(args.wiki).resolve()
    if not wiki_dir.is_dir():
        print(f"index: wiki dir not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)
    pages = list(load_pages(wiki_dir))
    meta_dir = wiki_dir / ".meta"
    write_meta(meta_dir, pages)
    write_index_md(wiki_dir, pages, datetime.date.today())
    n = sum(1 for _, pt, _, _ in pages if pt is not None)
    print(f"indexed {n} page(s) -> {meta_dir} + {wiki_dir / 'index.md'}")


if __name__ == "__main__":
    main()
