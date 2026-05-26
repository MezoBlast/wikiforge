#!/usr/bin/env python3
"""build.py — assemble a portable bundle from a curator wiki.

Output: dist/<name>-v<version>/ containing wiki/, bin/, SKILL.md, MANIFEST.md,
VERSION, feedback.md. The curator-only machinery (.forge/, .obsidian/,
dashboards/, raw/, OBSIDIAN.md) is explicitly excluded.
"""
import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import schema_spec as S
import frontmatter as FM
import provenance as PR
import lint as LINT
import index
import wikilinks as WL


# meta files copied verbatim into the bundle (log.md is curator-side only).
# index.md is NOT here — it is rendered fresh by index.write_index_md so it
# reflects the shipped page set.
SHIPPED_META = {"manifest", "out_of_scope"}


def run_lint(wiki_dir, raw_dir):
    today = datetime.date.today()
    issues = LINT.lint(wiki_dir, raw_dir, S.STALE_DAYS, S.PLACEHOLDER_ROT_DAYS, today)
    errs = [i for i in issues if i.is_blocking()]
    if errs:
        for i in errs:
            print(i.fmt(), file=sys.stderr)
        raise SystemExit(f"build aborted: {len(errs)} lint error(s)")


def should_drop(slug, page_type, fm, drop_placeholder):
    if page_type is None:
        return False
    if not isinstance(fm, dict):
        return False
    if fm.get("draft") is True:
        return True
    if drop_placeholder and fm.get("confidence") == "placeholder":
        return True
    return False


def validate_no_dangling_refs(kept_pages, kept_slugs):
    """Fail the build if any prose [[wikilink]] or frontmatter typed-edge in
    `kept_pages` points at a slug not in `kept_slugs`.

    Emits one diagnostic line per dangling ref on stderr, sorted by
    (from_slug, source, target), then raises SystemExit with the total
    count. The order is deterministic so curators can diff successive runs.
    """
    basename_index = {}
    for slug in kept_slugs:
        bn = slug.rsplit("/", 1)[-1]
        basename_index.setdefault(bn, []).append(slug)

    def resolves(target):
        return WL.resolve(WL.normalize_target(target), kept_slugs, basename_index) is not None

    dangling = []  # list of (from_slug, source, target)
    for slug, pt, fm, body in kept_pages:
        if pt is None:
            continue  # meta files like manifest.md have no slug-typed refs to validate
        if isinstance(fm, dict):
            for edge, target in WL.extract_frontmatter_edges(fm):
                if not resolves(target):
                    dangling.append((slug, f"frontmatter:{edge}", target))
        if isinstance(body, str):
            for target in WL.extract_prose_links(body):
                if not resolves(target):
                    dangling.append((slug, "body", target))

    if not dangling:
        return
    dangling.sort()
    for from_slug, source, target in dangling:
        print(f"dangling-ref: {from_slug}  {source}  -->  [[{target}]]",
              file=sys.stderr)
    raise SystemExit(f"build aborted: {len(dangling)} dangling reference(s)")


def copy_snippets(raw_dir, kept, out_snippets):
    out_snippets.mkdir(parents=True, exist_ok=True)
    for slug, pt, fm, _ in kept:
        if pt != "code-pattern" or not isinstance(fm, dict):
            continue
        try:
            text = PR.extract(
                raw_dir, fm["repo"], fm["commit"], fm["path"], fm["lines"]
            )
        except PR.ProvenanceError as e:
            raise SystemExit(f"snippet extraction failed for {slug}: {e}")
        bn = slug.rsplit("/", 1)[-1]
        (out_snippets / f"{bn}.txt").write_text(text, encoding="utf-8")


def get_git_sha(workspace):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=workspace, stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def render_template(path, subs):
    """Render a bundle-build template. Bundle templates use @VAR@ delimiters,
    distinct from bootstrap's {{var}} delimiters, so the two substitution
    passes can never collide."""
    text = Path(path).read_text(encoding="utf-8")
    for k, v in subs.items():
        text = text.replace("@" + k + "@", str(v))
    return text


def scope_summary_from_manifest(body):
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "<!--", "---")):
            return line[:200]
    return ""


def build(workspace, version, drop_placeholder, do_tar):
    workspace = Path(workspace).resolve()
    wiki_dir = workspace / "wiki"
    raw_dir = workspace / "raw"
    bin_dir = workspace / "bin"
    tpl_dir = workspace / ".forge" / "templates"

    if not (wiki_dir / "manifest.md").exists():
        raise SystemExit(f"build: not a wikiforge workspace (no {wiki_dir}/manifest.md)")

    manifest_fm, manifest_body = FM.load(wiki_dir / "manifest.md")
    name = manifest_fm.get("name") or workspace.name.replace("wikiforge-", "")

    print(f"==> build {name} v{version} from {workspace}")
    print("==> linting (strict)")
    run_lint(wiki_dir, raw_dir)

    bundle = workspace / "dist" / f"{name}-v{version}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    out_wiki = bundle / "wiki"
    out_wiki.mkdir()
    out_meta = out_wiki / ".meta"
    out_meta.mkdir()

    all_pages = list(index.load_pages(wiki_dir))
    kept = [p for p in all_pages if not should_drop(p[0], p[1], p[2], drop_placeholder)]
    kept_slugs = {slug for slug, pt, _, _ in kept if pt is not None}
    n_dropped = len(all_pages) - len(kept)
    print(f"    kept {len(kept)} pages ({n_dropped} dropped via draft/placeholder filter)")

    for slug, pt, fm, body in kept:
        if pt is None and slug in SHIPPED_META:
            (out_wiki / f"{slug}.md").write_text(body, encoding="utf-8")
            continue
        if pt is None:
            continue  # log.md or unknown meta — skip
        out_path = out_wiki / f"{slug}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(FM.dump(fm, body), encoding="utf-8")

    print("==> indexing")
    index.write_index_md(out_wiki, kept, datetime.date.today())
    index.write_pages_tsv(out_meta, kept)
    index.write_links_tsv(out_meta, kept, kept_slugs)

    print("==> extracting snippets")
    copy_snippets(raw_dir, kept, out_wiki / "snippets")

    print("==> copying bin/")
    out_bin = bundle / "bin"
    out_bin.mkdir()
    if bin_dir.exists():
        for f in sorted(bin_dir.iterdir()):
            if f.is_file():
                shutil.copy2(f, out_bin / f.name)
                (out_bin / f.name).chmod(0o755)

    print("==> rendering SKILL.md, MANIFEST.md, VERSION")
    sha = get_git_sha(workspace)
    today = datetime.date.today().isoformat()
    by_type = {}
    for slug, pt, fm, _ in kept:
        if pt is not None:
            by_type[pt] = by_type.get(pt, 0) + 1
    stats = "\n".join(f"- {pt}: {by_type.get(pt, 0)}" for pt in S.PAGE_TYPES)
    subs = {
        "NAME": name,
        "VERSION": version,
        "DATE": today,
        "SCHEMA_VERSION": str(S.SCHEMA_VERSION),
        "SHA": sha[:12] if sha != "unknown" else "unknown",
        "SCOPE_SUMMARY": scope_summary_from_manifest(manifest_body) or f"Wiki for {name}.",
        "STATS": stats,
        "PAGE_COUNT": str(sum(by_type.values())),
    }
    skill_tpl = tpl_dir / "SKILL.md.tmpl"
    manifest_tpl = tpl_dir / "MANIFEST.md.tmpl"
    if skill_tpl.exists():
        (bundle / "SKILL.md").write_text(render_template(skill_tpl, subs), encoding="utf-8")
    if manifest_tpl.exists():
        (bundle / "MANIFEST.md").write_text(render_template(manifest_tpl, subs), encoding="utf-8")

    (bundle / "VERSION").write_text(
        f"{version}\nsha:{sha}\nbuilt:{today}T00:00:00Z\nschema:{S.SCHEMA_VERSION}\n",
        encoding="utf-8",
    )
    (bundle / "feedback.md").write_text(
        "# feedback.md\n\n"
        "Consumer agents: append observations here (gaps, surprising accuracy, claims that turned out wrong). "
        "The curator harvests this periodically and routes items into the explorer queue.\n\n",
        encoding="utf-8",
    )

    print(f"==> bundle ready: {bundle}")
    if do_tar:
        tarball = bundle.parent / f"{name}-v{version}.tar.gz"
        subprocess.check_call(
            ["tar", "czf", str(tarball), "-C", str(bundle.parent), bundle.name]
        )
        print(f"==> tarball: {tarball}")


def main():
    p = argparse.ArgumentParser(prog="build", description="wikiforge bundle builder")
    p.add_argument("--workspace", default=".", help="curator workspace root (default: cwd)")
    p.add_argument("--version", required=True, help="semver, e.g. 0.1.0")
    p.add_argument("--keep-placeholders", action="store_true",
                   help="include pages with confidence: placeholder (default: drop)")
    p.add_argument("--tar", action="store_true", help="also create a .tar.gz of the bundle")
    args = p.parse_args()
    build(args.workspace, args.version, not args.keep_placeholders, args.tar)


if __name__ == "__main__":
    main()
