# Backward-Citation Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `.forge/lib/citations.py` sweep tool that discovers later papers citing the wiki's seed papers via Semantic Scholar, plus explorer SKILL.md integration as signal (e).

**Architecture:** `citations.py` is a sibling of `lint.py` — pure-logic core (seed extraction, co-citing counts, cache re-surface rule, report rendering) with a thin dependency-injected network layer over the Semantic Scholar Graph API. It writes `.forge/citations-report.md` (derived, ranked candidates) and `.forge/citations-cache.json` (derived state). The explorer agent consumes the report and applies judgment (scope, scoring, slating); the script never queues or fetches papers.

**Tech Stack:** Python 3 stdlib (`urllib`, `json`, `argparse`, `unittest`, `unittest.mock`) + existing `.forge/lib` helpers (`frontmatter.py`, `credentials.py`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-07-backward-citation-discovery-design.md`

## Global Constraints

- Key name: `SEMANTIC_SCHOLAR_API_KEY`, loaded via `credentials.load_credentials()` from `.forge/secrets/credentials.env`; env var overrides file. Key absent → print `sweep skipped: no SEMANTIC_SCHOLAR_API_KEY`, exit **0**. Never file a request-human for the key.
- Cadence: `--sweep` no-ops if last sweep < **14** days ago; `--force` overrides.
- Exit codes: **0** = swept or legitimately skipped; **2** = API failure after backoff (cache left untouched).
- API: `https://api.semanticscholar.org/graph/v1/paper/arXiv:<id>/citations`, fields `title,year,venue,externalIds,citationCount`, page size 100, ~1.1 s throttle between requests, backoff schedule 5 s / 20 s / 60 s on 429/5xx, HTTP 404 for a seed = skip that seed (not fatal).
- Re-surface rule: a candidate appears in a report only if its co-citing count **exceeds** the cached count from its last appearance. Dedup: candidates whose arXiv ID is a seed or already under `raw/papers/` never appear.
- Spec deviation (deliberate): seed extraction reads frontmatter `url:` then `source_path:` — **never the page body**, which cites other papers and would poison the seed set.
- Append-only files (`wiki/log.md`, `.forge/log.md`, `.forge/queue.md`, …) are not touched by any task. `citations-cache.json` / `citations-report.md` are mutable derived state (same category as `.forge/lint-report.md`).
- The script performs no scope judgment, no scoring, no fetching, no queueing.

---

### Task 1: Pure-logic core of `citations.py`

**Files:**
- Create: `.forge/lib/citations.py`
- Test: `.forge/lib/tests/test_citations.py`

**Interfaces:**
- Consumes: `frontmatter.split(text) -> (dict, str)` from `.forge/lib/frontmatter.py`.
- Produces (used by Task 2's `main()`):
  - `extract_seed_ids(sources_dir=SOURCES_DIR) -> dict[str, str]` — arXiv id → source-page slug
  - `known_arxiv_ids(seeds: dict, papers_dir=PAPERS_DIR) -> set[str]`
  - `compute_co_citing(citers_by_seed: dict[str, list[dict]], seeds: dict[str, str]) -> dict[str, dict]` — key = arXiv id or S2 paperId; value = `{"id", "arxiv": bool, "title", "year", "seeds": [slug,...]}`
  - `filter_new(candidates: dict, cache: dict, known_ids: set) -> dict`
  - `load_cache(path=CACHE_PATH) -> dict` / `save_cache(cache, path=CACHE_PATH)` — shape `{"last_sweep": str|None, "seen": {id: int}}`
  - `should_run(cache, now: datetime, force=False) -> bool`
  - `render_report(candidates: dict, now: datetime) -> str`
  - Constants: `SWEEP_INTERVAL_DAYS = 14`, `CACHE_PATH`, `REPORT_PATH`, `SOURCES_DIR`, `PAPERS_DIR`

- [ ] **Step 1: Write the failing tests**

Create `.forge/lib/tests/test_citations.py`:

```python
"""Tests for citations.py pure logic. Run: python3 .forge/lib/tests/test_citations.py"""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import citations as C

UTC = datetime.timezone.utc


def make_source(dir_, slug, url=None, source_path=None, body=""):
    fm = ['---', f'title: "{slug}"', 'type: source']
    if url:
        fm.append(f'url: {url}')
    if source_path:
        fm.append(f'source_path: "{source_path}"')
    fm.append('---')
    (dir_ / f"{slug}.md").write_text("\n".join(fm) + "\n" + body, encoding="utf-8")


class TestSeedExtraction(unittest.TestCase):
    def test_extracts_from_url_and_source_path_but_never_body(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            make_source(d, "via-url", url="https://arxiv.org/abs/2312.14867")
            make_source(d, "via-path", source_path="raw/papers/2310.01596.pdf")
            make_source(d, "repo-page", body="cites https://arxiv.org/abs/9999.11111 in body")
            seeds = C.extract_seed_ids(d)
            self.assertEqual(seeds, {"2312.14867": "via-url", "2310.01596": "via-path"})

    def test_version_suffix_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            make_source(d, "versioned", url="https://arxiv.org/abs/2605.08703v1")
            self.assertEqual(C.extract_seed_ids(d), {"2605.08703": "versioned"})


class TestKnownIds(unittest.TestCase):
    def test_seeds_and_raw_pdfs_are_known(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "2411.15738.pdf").touch()
            (d / "2605.08703v1.pdf").touch()
            (d / "kingma-2015-adam.pdf").touch()  # non-arxiv name ignored
            known = C.known_arxiv_ids({"2312.14867": "seed"}, d)
            self.assertEqual(known, {"2312.14867", "2411.15738", "2605.08703"})


def citer(title, arxiv=None, paper_id="s2pid", year=2026):
    ext = {"ArXiv": arxiv} if arxiv else {}
    return {"title": title, "year": year, "externalIds": ext, "paperId": paper_id}


class TestCoCiting(unittest.TestCase):
    def test_counts_seeds_per_citer(self):
        seeds = {"1111.11111": "seed-a", "2222.22222": "seed-b"}
        by_seed = {
            "1111.11111": [citer("P", arxiv="3333.33333"), citer("Q", paper_id="qq")],
            "2222.22222": [citer("P", arxiv="3333.33333")],
        }
        cands = C.compute_co_citing(by_seed, seeds)
        self.assertEqual(sorted(cands["3333.33333"]["seeds"]), ["seed-a", "seed-b"])
        self.assertTrue(cands["3333.33333"]["arxiv"])
        self.assertEqual(cands["qq"]["seeds"], ["seed-a"])
        self.assertFalse(cands["qq"]["arxiv"])


class TestFilterNew(unittest.TestCase):
    def cands(self):
        return {
            "3333.33333": {"id": "3333.33333", "arxiv": True, "title": "P", "year": 2026, "seeds": ["a", "b"]},
            "4444.44444": {"id": "4444.44444", "arxiv": True, "title": "K", "year": 2025, "seeds": ["a"]},
            "qq": {"id": "qq", "arxiv": False, "title": "Q", "year": 2026, "seeds": ["a"]},
        }

    def test_known_ids_dropped(self):
        out = C.filter_new(self.cands(), {"seen": {}}, known_ids={"4444.44444"})
        self.assertNotIn("4444.44444", out)
        self.assertIn("3333.33333", out)

    def test_resurface_only_when_count_increases(self):
        cache = {"seen": {"3333.33333": 2}}
        self.assertNotIn("3333.33333", C.filter_new(self.cands(), cache, set()))
        cache = {"seen": {"3333.33333": 1}}
        self.assertIn("3333.33333", C.filter_new(self.cands(), cache, set()))

    def test_no_arxiv_citers_need_co_citing_2(self):
        out = C.filter_new(self.cands(), {"seen": {}}, set())
        self.assertNotIn("qq", out)  # co-citing 1, no arXiv id -> noise, dropped


class TestCadence(unittest.TestCase):
    def test_gate(self):
        now = datetime.datetime(2026, 7, 7, tzinfo=UTC)
        self.assertTrue(C.should_run({"last_sweep": None, "seen": {}}, now))
        recent = {"last_sweep": "2026-07-01T00:00:00+00:00", "seen": {}}
        self.assertFalse(C.should_run(recent, now))
        self.assertTrue(C.should_run(recent, now, force=True))
        old = {"last_sweep": "2026-06-01T00:00:00+00:00", "seen": {}}
        self.assertTrue(C.should_run(old, now))


class TestCache(unittest.TestCase):
    def test_roundtrip_and_corrupt_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cache.json"
            self.assertEqual(C.load_cache(p), {"last_sweep": None, "seen": {}})
            C.save_cache({"last_sweep": "2026-07-07T00:00:00+00:00", "seen": {"x": 2}}, p)
            self.assertEqual(C.load_cache(p)["seen"], {"x": 2})
            p.write_text("{corrupt", encoding="utf-8")
            self.assertEqual(C.load_cache(p), {"last_sweep": None, "seen": {}})


class TestReport(unittest.TestCase):
    def test_render_ranks_by_co_citing_and_escapes_pipes(self):
        now = datetime.datetime(2026, 7, 7, tzinfo=UTC)
        cands = {
            "4444.44444": {"id": "4444.44444", "arxiv": True, "title": "one|seed", "year": 2025, "seeds": ["a"]},
            "3333.33333": {"id": "3333.33333", "arxiv": True, "title": "two seeds", "year": 2026, "seeds": ["a", "b"]},
            "qq": {"id": "qq", "arxiv": False, "title": "no arxiv", "year": 2026, "seeds": ["a", "b"]},
        }
        rep = C.render_report(cands, now)
        self.assertLess(rep.index("3333.33333"), rep.index("4444.44444"))
        self.assertIn("one\\|seed", rep)
        self.assertIn("Citers without arXiv IDs", rep)
        self.assertIn("S2 paperId `qq`", rep)

    def test_empty_report(self):
        now = datetime.datetime(2026, 7, 7, tzinfo=UTC)
        self.assertIn("No new candidates", C.render_report({}, now))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 .forge/lib/tests/test_citations.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'citations'`

- [ ] **Step 3: Write the implementation**

Create `.forge/lib/citations.py`:

```python
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


if __name__ == "__main__":
    print("citations.py: main() arrives in the next task; nothing to run yet",
          file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 .forge/lib/tests/test_citations.py`
Expected: `OK` (11 tests)

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/citations.py .forge/lib/tests/test_citations.py
git commit -m "feat(forge): citations.py core — seeds, co-citing, cache, report"
```

---

### Task 2: CLI wiring — `main()`, key gate, sweep orchestration

**Files:**
- Modify: `.forge/lib/citations.py` (replace the `__main__` stub at the bottom)
- Test: `.forge/lib/tests/test_citations.py` (append)

**Interfaces:**
- Consumes: everything from Task 1, exact signatures as listed there; `credentials.load_credentials()` (already imported).
- Produces: `main(argv=None) -> int` and the CLI contract used by Task 3's SKILL.md text: `python3 .forge/lib/citations.py --sweep [--force]`, exit 0/2, skip message `sweep skipped: no SEMANTIC_SCHOLAR_API_KEY`.

- [ ] **Step 1: Write the failing tests**

Append to `.forge/lib/tests/test_citations.py` (before the `if __name__` block):

```python
import io
import unittest.mock as mock


def fake_opener_pages(pages):
    """Opener returning successive JSON pages; raises if called too often."""
    it = iter(pages)

    def opener(req, timeout=30):
        return io.BytesIO(json.dumps(next(it)).encode())
    return opener


class TestFetchCiters(unittest.TestCase):
    def test_pagination_follows_next(self):
        pages = [
            {"data": [{"citingPaper": citer("A", arxiv="5555.55555")}], "next": 100},
            {"data": [{"citingPaper": citer("B", arxiv="6666.66666")}]},
        ]
        got = C.fetch_citers("1111.11111", "k", sleep=lambda s: None,
                             opener=fake_opener_pages(pages))
        self.assertEqual([p["title"] for p in got], ["A", "B"])

    def test_404_seed_returns_empty(self):
        def opener(req, timeout=30):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        self.assertEqual(
            C.fetch_citers("1111.11111", "k", sleep=lambda s: None, opener=opener), [])

    def test_persistent_429_raises_sweep_error(self):
        def opener(req, timeout=30):
            raise urllib.error.HTTPError(req.full_url, 429, "tm", {}, None)
        with self.assertRaises(C.SweepError):
            C.fetch_citers("1111.11111", "k", sleep=lambda s: None, opener=opener)


class TestMainKeyGate(unittest.TestCase):
    def test_no_key_skips_with_exit_0(self):
        with mock.patch.object(C, "load_credentials", return_value={}), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = C.main(["--sweep"])
            self.assertEqual(rc, 0)
            self.assertIn("sweep skipped: no SEMANTIC_SCHOLAR_API_KEY", buf.getvalue())
```

Also add `import os` and `import urllib.error` to the test file's imports.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 .forge/lib/tests/test_citations.py`
Expected: `TestMainKeyGate` FAILS with `AttributeError: ... no attribute 'main'`; `TestFetchCiters` passes (Task 1 shipped `fetch_citers`).

- [ ] **Step 3: Implement `main()`**

In `.forge/lib/citations.py`, replace the entire `if __name__ == "__main__":` stub with:

```python
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
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python3 .forge/lib/tests/test_citations.py`
Expected: `OK` (15 tests)

- [ ] **Step 5: Verify the live key gate end-to-end**

Run: `python3 .forge/lib/citations.py --sweep; echo "exit=$?"`
Expected (key is not provisioned in this workspace yet): `sweep skipped: no SEMANTIC_SCHOLAR_API_KEY` then `exit=0`. No cache or report file created: `ls .forge/citations-* 2>/dev/null` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add .forge/lib/citations.py .forge/lib/tests/test_citations.py
git commit -m "feat(forge): citations.py CLI — key gate, cadence, sweep orchestration"
```

---

### Task 3: Explorer SKILL.md integration (signal e) + credentials placeholder

**Files:**
- Modify: `.forge/skills/explorer/SKILL.md` (two edits: after signal (d) ~line 53; scoring table ~line 69)
- Modify: `.forge/secrets/credentials.env` (append commented placeholder; file is gitignored — not part of the commit)

**Interfaces:**
- Consumes: the Task 2 CLI contract (`--sweep`, exit 0/2, report path `.forge/citations-report.md`).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add signal (e) to the explorer skill**

In `.forge/skills/explorer/SKILL.md`, insert after the signal (d) paragraph (which ends `— it has been slated before.`) and before `### 2. Plan a bounded slate`:

~~~markdown
**e) Backward citations (cited-by sweep).** Requires `SEMANTIC_SCHOLAR_API_KEY`
in `.forge/secrets/credentials.env`. The key is bootstrap-provisioned — if it
is absent, note `signal e skipped: no S2 key` in your run log and move on;
**never** file a request-human for it. Run:

```sh
python3 .forge/lib/citations.py --sweep
cat .forge/citations-report.md
```

The script no-ops (exit 0) when the key is absent or the last sweep is
< 14 days old, and exits 2 on API failure — none of these block the run;
proceed with signals a–d. On success the report ranks later papers that cite
the wiki's seed papers by **co-citing score** — how many seeds the citer
cites, the forward-in-time mirror of the co-citation score in signal (c).
Drop candidates that fall under `wiki/out_of_scope.md`, score the rest
(table below). arXiv candidates use the standard arXiv fetch recipe; entries
under "Citers without arXiv IDs" use the non-arxiv recipe. Queue-note
convention: `cited-by sweep; co-cites 3 seeds (viescore, imagenhub, aurora)`.
~~~

- [ ] **Step 2: Add the three scoring rows**

In the scoring table, insert directly under the `Citation-chain target with co-citation score = 1` row:

```markdown
| Cited-by candidate with co-citing score ≥ 3                              | 50    |
| Cited-by candidate with co-citing score = 2                              | 30    |
| Cited-by candidate with co-citing score = 1                              | 10 — usually defer |
```

- [ ] **Step 3: Append the credentials placeholder**

```bash
grep -q "SEMANTIC_SCHOLAR_API_KEY" .forge/secrets/credentials.env || \
  printf '\n# Semantic Scholar Graph API key — enables the explorer cited-by sweep\n# (.forge/lib/citations.py). Bootstrap-provisioned; free at semanticscholar.org/product/api\n# SEMANTIC_SCHOLAR_API_KEY=\n' >> .forge/secrets/credentials.env
```

Verify: `grep -A1 "Semantic Scholar" .forge/secrets/credentials.env` shows the commented block.

- [ ] **Step 4: Sanity-check the skill doc renders correctly**

Run: `grep -n "co-citing" .forge/skills/explorer/SKILL.md`
Expected: hits in the signal (e) block and three scoring-table rows, none elsewhere.

Run: `python3 .forge/lib/lint.py --report >/dev/null; echo "lint exit=$?"`
Expected: `lint exit=0` (skill docs aren't linted, but this proves nothing broke).

- [ ] **Step 5: Commit**

```bash
git add .forge/skills/explorer/SKILL.md
git commit -m "feat(explorer): signal (e) backward-citation sweep + co-citing scoring"
```

---

### Task 4: Verification against the spec's test section

**Files:**
- No new files. Exercises `.forge/lib/citations.py` and reads `.forge/citations-report.md`.

**Interfaces:**
- Consumes: the full CLI contract from Task 2.

- [ ] **Step 1: Full unit suite**

Run: `python3 .forge/lib/tests/test_citations.py`
Expected: `OK` (15 tests)

- [ ] **Step 2: Keyless skip path (live)**

Run: `python3 .forge/lib/citations.py --sweep; echo "exit=$?"`
Expected: skip message, `exit=0`.

- [ ] **Step 3: Seed extraction sanity (live, no network)**

Run: `python3 -c "import sys; sys.path.insert(0,'.forge/lib'); import citations; s=citations.extract_seed_ids(); print(len(s), 'seeds'); [print(' ', k, '->', v) for k,v in sorted(s.items())]"`
Expected: ≥ 10 seeds; must include `2312.14867 -> viescore-paper` and `2310.01596 -> imagenhub-paper`; must NOT include arXiv ids that appear only in page bodies. `edit-r1-repo` and `editreward-repo` (repo sources) must be absent.

- [ ] **Step 4: Keyed live sweep — only if the key has been provisioned**

If `SEMANTIC_SCHOLAR_API_KEY` is present in `.forge/secrets/credentials.env`:

Run: `python3 .forge/lib/citations.py --sweep --force && head -40 .forge/citations-report.md`
Expected per spec §5: ADIEE (arXiv 2507.07317, already in `raw/papers/`) absent from the report; the 2026-03 instruction-editing survey present with co-citing ≥ 2.

Then re-run `python3 .forge/lib/citations.py --sweep; echo "exit=$?"` — expected: cadence-gate skip, `exit=0`.
Then `python3 .forge/lib/citations.py --sweep --force` — expected: `0 new candidates` (unchanged counts are suppressed by the re-surface rule).

If the key is absent: record in the final report to the human that the keyed live sweep is **pending key provisioning**, with the exact command above. Do not fake it, do not run keyless workarounds.

- [ ] **Step 5: Commit any cache/report artifacts produced by a keyed run**

```bash
git status --short .forge/citations-*
# if files exist:
git add .forge/citations-cache.json .forge/citations-report.md
git commit -m "chore(forge): first cited-by sweep artifacts"
```

Skip this step entirely if no keyed run happened.
