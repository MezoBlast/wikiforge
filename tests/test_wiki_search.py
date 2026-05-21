import os
import subprocess
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin" / "wiki-search"


def _make_wiki(root):
    meta = root / "wiki" / ".meta"
    meta.mkdir(parents=True)
    (meta / "pages.tsv").write_text(
        "path\ttitle\ttype\ttags\tlast_verified\tconfidence\n"
        "concepts/vision-language-fusion\tVision-language fusion strategies\t"
        "concept\tfusion,vision-encoder\t2026-05-21\tlow\n"
        "code-patterns/siglip-projector\tMLP projector connecting a SigLIP encoder to an LLM\t"
        "code-pattern\tprojector,siglip\t2026-05-21\tlikely\n"
    )
    c = root / "wiki" / "concepts"
    c.mkdir(parents=True)
    (c / "vision-language-fusion.md").write_text(
        "# Vision-language fusion strategies\n\n"
        "Canonical strategies for fusing a vision encoder with a language model.\n"
    )
    cp = root / "wiki" / "code-patterns"
    cp.mkdir(parents=True)
    (cp / "siglip-projector.md").write_text(
        "# MLP projector\n\n"
        "Connect a frozen vision encoder to an LLM through a projector.\n"
    )


def _search(root, *args):
    return subprocess.run(
        [str(BIN), *args],
        env={**os.environ, "WIKI_ROOT": str(root)},
        capture_output=True, text=True,
    )


def test_multiword_natural_language_query_matches(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "fusing a vision encoder with a language model")
    assert r.returncode == 0, r.stderr
    assert "concepts/vision-language-fusion" in r.stdout


def test_term_order_does_not_matter(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "projector encoder vision")
    assert "code-patterns/siglip-projector" in r.stdout


def test_type_filter_still_works(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "--type", "concept", "projector vision encoder")
    assert "concepts/vision-language-fusion" in r.stdout
    assert "code-patterns/siglip-projector" not in r.stdout


def test_ranking_prefers_more_matched_terms(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "vision encoder projector llm")
    hits = [ln for ln in r.stdout.splitlines() if ln.startswith("[score")]
    assert hits, r.stdout
    # the projector page matches projector+encoder+llm; fusion page matches fewer
    assert "code-patterns/siglip-projector" in hits[0]


def test_missing_index_errors(tmp_path):
    r = _search(tmp_path, "anything")
    assert r.returncode == 1
    assert "no" in r.stderr.lower()
