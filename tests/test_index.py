import index


def _page(text):
    return "---\n" + text + "\n---\n\nbody\n"


def _concept(title, extra=""):
    return _page(
        f"title: {title}\ntype: concept\n"
        f"created: 2026-01-01\nlast_verified: 2026-01-01\nconfidence: likely" + extra
    )


def test_load_pages_classifies_pages_and_meta(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(_concept("SGD"), encoding="utf-8")
    (wiki / "manifest.md").write_text("# manifest\n", encoding="utf-8")
    pages = {slug: pt for slug, pt, _, _ in index.load_pages(wiki)}
    assert pages["concepts/sgd"] == "concept"
    assert pages["manifest"] is None  # meta file -> page_type None


def test_write_meta_writes_both_tsvs(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(_concept("SGD"), encoding="utf-8")
    meta = wiki / ".meta"
    index.write_meta(meta, index.load_pages(wiki))
    pages_tsv = (meta / "pages.tsv").read_text(encoding="utf-8")
    assert pages_tsv.splitlines()[0] == "path\ttitle\ttype\ttags\tlast_verified\tconfidence"
    assert "concepts/sgd\tSGD\tconcept\t" in pages_tsv
    links_tsv = (meta / "links.tsv").read_text(encoding="utf-8")
    assert links_tsv.splitlines()[0] == "from\tto\tedge_type"


def test_write_links_typed_edge_wins_over_prose(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "claims").mkdir(parents=True)
    (wiki / "claims" / "b.md").write_text(
        _page("title: B\ntype: claim\ncreated: 2026-01-01\nlast_verified: 2026-01-01\n"
              "confidence: likely\nstatus: open\nevidence: [sources/x]\ncounter_evidence: []"),
        encoding="utf-8")
    (wiki / "claims" / "a.md").write_text(
        "---\ntitle: A\ntype: claim\ncreated: 2026-01-01\nlast_verified: 2026-01-01\n"
        "confidence: likely\nstatus: open\nevidence: [sources/x]\ncounter_evidence: []\n"
        "supersedes: [claims/b]\n---\n\nSee [[claims/b]] for the older view.\n",
        encoding="utf-8")
    meta = wiki / ".meta"
    index.write_meta(meta, index.load_pages(wiki))
    links = (meta / "links.tsv").read_text(encoding="utf-8")
    assert "claims/a\tclaims/b\tsupersedes" in links
    assert "claims/a\tclaims/b\treferences" not in links  # typed edge won


def test_main_indexes_draft_pages(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "draft-page.md").write_text(
        _concept("Draft", extra="\ndraft: true"), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["index", "--wiki", str(wiki)])
    index.main()
    pages_tsv = (wiki / ".meta" / "pages.tsv").read_text(encoding="utf-8")
    assert "concepts/draft-page" in pages_tsv  # curator index keeps drafts


def test_pages_tsv_absent_last_verified_is_empty(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    # a page missing last_verified (malformed; the curator index does not lint)
    (wiki / "concepts" / "stub.md").write_text(
        _page("title: Stub\ntype: concept\ncreated: 2026-01-01\nconfidence: placeholder"),
        encoding="utf-8")
    meta = wiki / ".meta"
    index.write_meta(meta, index.load_pages(wiki))
    pages_tsv = (meta / "pages.tsv").read_text(encoding="utf-8")
    assert "\tNone\t" not in pages_tsv
    assert "concepts/stub\tStub\tconcept\t\t\tplaceholder" in pages_tsv


def test_write_index_md_groups_by_type(tmp_path):
    import datetime
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        "---\ntitle: SGD\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    pages = list(index.load_pages(wiki))
    index.write_index_md(wiki, pages, datetime.date(2026, 5, 21))
    txt = (wiki / "index.md").read_text(encoding="utf-8")
    assert "# Index" in txt
    assert "## concepts" in txt
    assert "[[concepts/sgd]] — SGD" in txt


def test_write_index_md_empty_type_renders_none(tmp_path):
    import datetime
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    index.write_index_md(wiki, [], datetime.date(2026, 5, 21))
    assert "_(none)_" in (wiki / "index.md").read_text(encoding="utf-8")


def test_index_main_writes_index_md(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        "---\ntitle: SGD\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["index", "--wiki", str(wiki)])
    index.main()
    assert (wiki / "index.md").exists()
    assert (wiki / ".meta" / "pages.tsv").exists()


def test_write_links_tsv_raises_on_unresolved_prose_target(tmp_path):
    """Defense-in-depth: validate_no_dangling_refs should catch this upstream,
    but if a caller bypasses it, write_links_tsv must fail loudly."""
    import pytest
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "a.md").write_text(
        _page("title: A\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    pages = list(index.load_pages(wiki))
    # Body has no dangling refs yet — inject one manually to simulate
    # a caller bypassing validate_no_dangling_refs:
    pages = [(slug, pt, fm, "See [[concepts/does-not-exist]].")
             for slug, pt, fm, body in pages if pt == "concept"]
    meta = wiki / ".meta"
    meta.mkdir()
    with pytest.raises(RuntimeError, match="unresolved target"):
        index.write_links_tsv(meta, pages, {"concepts/a"})
