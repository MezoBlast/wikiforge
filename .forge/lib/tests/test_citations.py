"""Tests for citations.py pure logic. Run: python3 .forge/lib/tests/test_citations.py"""
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import unittest.mock as mock
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


if __name__ == "__main__":
    unittest.main()
