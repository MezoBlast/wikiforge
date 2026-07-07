#!/usr/bin/env python3
"""citations.py — backward-citation (cited-by) sweep via Semantic Scholar.

Discovers later papers that cite the wiki's seed papers (wiki/sources/ pages
with an arXiv URL), computes co-citing counts (how many seeds each citer
cites — the forward mirror of the explorer's co-citation score), and writes
a ranked candidate report for the explorer skill's signal (e).

Modes:
  --sweep            run the sweep; no-op if last sweep < 14 days ago
  --force            override the cadence gate

Gating: requires SEMANTIC_SCHOLAR_API_KEY (env or .forge/secrets/
credentials.env). Absent key -> skip message, exit 0.
Exit codes: 0 = swept or legitimately skipped; 2 = API failure after backoff.

Mechanics only: no scope judgment, no scoring, no fetching, no queueing —
those are the explorer agent's job (see .forge/skills/explorer/SKILL.md).
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import frontmatter as FM
from credentials import load_credentials

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "wiki" / "sources"
PAPERS_DIR = ROOT / "raw" / "papers"
CACHE_PATH = ROOT / ".forge" / "citations-cache.json"
REPORT_PATH = ROOT / ".forge" / "citations-report.md"

S2_BASE = "https://api.semanticscholar.org/graph/v1"
CITATION_FIELDS = "title,year,venue,externalIds,citationCount"
PAGE_SIZE = 100
THROTTLE_SECONDS = 1.1
BACKOFF_SCHEDULE = [5, 20, 60]
SWEEP_INTERVAL_DAYS = 14

ARXIV_ID = r"(\d{4}\.\d{4,5})"
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/" + ARXIV_ID + r"(?:v\d+)?")
ARXIV_PDF_RE = re.compile(ARXIV_ID + r"(?:v\d+)?$")


class SweepError(Exception):
    """API gave up after backoff; the sweep run is abandoned."""


# ---------- seed extraction ----------

def extract_seed_ids(sources_dir=SOURCES_DIR):
    """arXiv id -> source-page slug, from frontmatter url:/source_path: only.

    The body is deliberately ignored: it cites *other* papers, which would
    poison the seed set. Pages without an arXiv reference (repos, web
    clips) are skipped — that is normal, not an error.
    """
    seeds = {}
    for page in sorted(Path(sources_dir).glob("*.md")):
        try:
            fm, _body = FM.split(page.read_text(encoding="utf-8"))
        except FM.FrontmatterError:
            continue
        m = ARXIV_URL_RE.search(str(fm.get("url") or ""))
        if not m:
            m = ARXIV_PDF_RE.search(Path(str(fm.get("source_path") or "")).stem)
        if m:
            seeds[m.group(1)] = page.stem
    return seeds


def known_arxiv_ids(seeds, papers_dir=PAPERS_DIR):
    """IDs already in the workspace: seeds themselves + raw/papers/ PDFs."""
    known = set(seeds)
    for pdf in Path(papers_dir).glob("*.pdf"):
        m = ARXIV_PDF_RE.match(pdf.stem)
        if m:
            known.add(m.group(1))
    return known


# ---------- Semantic Scholar fetch ----------

def _get_json(url, api_key, *, sleep=time.sleep, opener=None):
    """GET a JSON document with backoff on 429/5xx.

    Returns None on HTTP 404 (seed unknown to S2 — caller skips it).
    Raises SweepError after exhausting BACKOFF_SCHEDULE.
    """
    opener = opener or urllib.request.urlopen
    last_err = None
    for wait in [0] + BACKOFF_SCHEDULE:
        if wait:
            sleep(wait)
        req = urllib.request.Request(url, headers={"x-api-key": api_key})
        try:
            with opener(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503, 504):
                last_err = e
                continue
            raise SweepError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            continue
    raise SweepError(f"gave up after {1 + len(BACKOFF_SCHEDULE)} attempts: {url} ({last_err})")


def fetch_citers(arxiv_id, api_key, *, sleep=time.sleep, opener=None):
    """All citers of one seed, paged. Returns list of citingPaper dicts."""
    citers, offset = [], 0
    while True:
        url = (f"{S2_BASE}/paper/arXiv:{arxiv_id}/citations"
               f"?fields={CITATION_FIELDS}&limit={PAGE_SIZE}&offset={offset}")
        data = _get_json(url, api_key, sleep=sleep, opener=opener)
        if data is None:
            return []
        citers.extend(c["citingPaper"] for c in data.get("data", []))
        if data.get("next") is None:
            return citers
        offset = data["next"]
        sleep(THROTTLE_SECONDS)


# ---------- co-citing + filtering ----------

def compute_co_citing(citers_by_seed, seeds):
    """Merge per-seed citer lists into candidates keyed by arXiv id (or S2
    paperId when the citer has no arXiv id)."""
    candidates = {}
    for seed_id, citers in citers_by_seed.items():
        slug = seeds[seed_id]
        for p in citers:
            aid = (p.get("externalIds") or {}).get("ArXiv")
            key = aid or p.get("paperId")
            if not key:
                continue
            entry = candidates.setdefault(key, {
                "id": key,
                "arxiv": bool(aid),
                "title": p.get("title") or "(untitled)",
                "year": p.get("year"),
                "seeds": [],
            })
            if slug not in entry["seeds"]:
                entry["seeds"].append(slug)
    return candidates


def filter_new(candidates, cache, known_ids):
    """Report-worthiness filter.

    - workspace dedup: arXiv candidates already present as seeds or under
      raw/papers/ never appear
    - re-surface rule: a candidate appears only if its co-citing count
      EXCEEDS its cached count (counts grow as the wiki gains seeds, so a
      deferred citer returns exactly when its priority rises)
    - citers without an arXiv id need co-citing >= 2 (manual fetch is
      expensive; single-seed ones are noise)
    """
    seen = cache.get("seen", {})
    out = {}
    for key, entry in candidates.items():
        count = len(entry["seeds"])
        if entry["arxiv"] and key in known_ids:
            continue
        if not entry["arxiv"] and count < 2:
            continue
        if count > seen.get(key, 0):
            out[key] = entry
    return out


# ---------- cache ----------

def load_cache(path=CACHE_PATH):
    p = Path(path)
    empty = {"last_sweep": None, "seen": {}}
    if not p.is_file():
        return empty
    try:
        cache = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty  # derived state: corrupt cache just means a fuller next report
    if not isinstance(cache, dict):
        return empty
    cache.setdefault("last_sweep", None)
    cache.setdefault("seen", {})
    return cache


def save_cache(cache, path=CACHE_PATH):
    Path(path).write_text(
        json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def should_run(cache, now, force=False):
    if force or not cache.get("last_sweep"):
        return True
    last = datetime.datetime.fromisoformat(cache["last_sweep"])
    return (now - last).days >= SWEEP_INTERVAL_DAYS


# ---------- report ----------

def render_report(candidates, now):
    arx = [e for e in candidates.values() if e["arxiv"]]
    other = [e for e in candidates.values() if not e["arxiv"]]
    lines = [
        "# citations report — backward-citation sweep",
        "",
        f"Generated: {now.isoformat(timespec='seconds')} by `.forge/lib/citations.py`.",
        "Derived file — regenerated each sweep; do not edit by hand.",
        "",
    ]
    if not arx and not other:
        lines.append("No new candidates this sweep.")
    if arx:
        lines += ["| arXiv ID | title | year | co-citing | seeds cited |",
                  "|---|---|---|---|---|"]
        for e in sorted(arx, key=lambda x: (-len(x["seeds"]), x["id"])):
            title = e["title"].replace("|", "\\|")
            lines.append(f"| {e['id']} | {title} | {e['year'] or '?'} "
                         f"| {len(e['seeds'])} | {', '.join(sorted(e['seeds']))} |")
    if other:
        lines += ["", "## Citers without arXiv IDs (manual fetch)", ""]
        for e in sorted(other, key=lambda x: (-len(x["seeds"]), x["id"])):
            lines.append(f"- {e['title']} ({e['year'] or '?'}) — co-cites "
                         f"{len(e['seeds'])}: {', '.join(sorted(e['seeds']))} "
                         f"— S2 paperId `{e['id']}`")
    return "\n".join(lines) + "\n"


# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="backward-citation (cited-by) sweep via Semantic Scholar")
    ap.add_argument("--sweep", action="store_true", help="run the cited-by sweep")
    ap.add_argument("--force", action="store_true",
                    help=f"ignore the {SWEEP_INTERVAL_DAYS}-day cadence gate")
    args = ap.parse_args(argv)
    if not args.sweep:
        ap.print_help()
        return 0

    load_credentials()
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if not api_key:
        print("sweep skipped: no SEMANTIC_SCHOLAR_API_KEY")
        return 0

    now = datetime.datetime.now(datetime.timezone.utc)
    cache = load_cache()
    if not should_run(cache, now, force=args.force):
        print(f"sweep skipped: last sweep {cache['last_sweep']} is less than "
              f"{SWEEP_INTERVAL_DAYS} days old (use --force to override)")
        return 0

    seeds = extract_seed_ids()
    if not seeds:
        print("sweep skipped: no arXiv seeds found in wiki/sources/")
        return 0

    print(f"sweeping {len(seeds)} seeds...")
    citers_by_seed = {}
    try:
        for i, seed_id in enumerate(sorted(seeds), 1):
            citers_by_seed[seed_id] = fetch_citers(seed_id, api_key)
            print(f"  [{i}/{len(seeds)}] arXiv:{seed_id} ({seeds[seed_id]}): "
                  f"{len(citers_by_seed[seed_id])} citers")
            time.sleep(THROTTLE_SECONDS)
    except SweepError as e:
        # cache untouched: the next run retries the whole sweep
        print(f"sweep failed: {e}", file=sys.stderr)
        return 2

    candidates = compute_co_citing(citers_by_seed, seeds)
    fresh = filter_new(candidates, cache, known_arxiv_ids(seeds))
    REPORT_PATH.write_text(render_report(fresh, now), encoding="utf-8")
    for key, entry in fresh.items():
        cache["seen"][key] = len(entry["seeds"])
    cache["last_sweep"] = now.isoformat(timespec="seconds")
    save_cache(cache)
    print(f"report: {REPORT_PATH.relative_to(ROOT)} ({len(fresh)} new candidates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
