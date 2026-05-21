import datetime

import lint


def _page(text):
    return (
        "---\n" + text + "\n---\n\nbody\n"
    )


def test_fix_rebuilds_index_from_pages(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: Stochastic Gradient Descent\ntype: concept\n"
              "created: 2026-01-01\nlast_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("stale placeholder content\n", encoding="utf-8")

    lint.fix(wiki, datetime.date(2026, 5, 20))

    idx = (wiki / "index.md").read_text(encoding="utf-8")
    assert "# Index" in idx
    assert "[[concepts/sgd]] — Stochastic Gradient Descent" in idx
    assert "stale placeholder" not in idx  # stale content was replaced


def test_fix_marks_empty_types_as_none(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)

    lint.fix(wiki, datetime.date(2026, 5, 20))

    idx = (wiki / "index.md").read_text(encoding="utf-8")
    assert "_(none)_" in idx  # an empty type renders as _(none)_


def test_stale_index_warns_when_meta_missing(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert any(i.code == "stale-index" for i in issues)


def test_stale_index_silent_when_meta_fresh(tmp_path):
    import os
    import time
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    meta = wiki / ".meta"
    meta.mkdir()
    pages_tsv = meta / "pages.tsv"
    pages_tsv.write_text("path\ttitle\ttype\ttags\tlast_verified\tconfidence\n",
                         encoding="utf-8")
    index_md = wiki / "index.md"
    index_md.write_text("# Index\n", encoding="utf-8")
    future = time.time() + 10
    os.utime(pages_tsv, (future, future))
    os.utime(index_md, (future, future))  # index newer than the page
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert not any(i.code == "stale-index" for i in issues)


def test_stale_index_warns_when_index_md_stale(tmp_path):
    import os
    import time
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    meta = wiki / ".meta"
    meta.mkdir()
    pages_tsv = meta / "pages.tsv"
    pages_tsv.write_text("path\ttitle\ttype\ttags\tlast_verified\tconfidence\n",
                         encoding="utf-8")
    index_md = wiki / "index.md"
    index_md.write_text("# Index\n", encoding="utf-8")
    future = time.time() + 100
    os.utime(pages_tsv, (future, future))   # .meta fresh
    past = time.time() - 100
    os.utime(index_md, (past, past))        # index.md stale
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    stale = [i for i in issues if i.code == "stale-index"]
    assert any("index.md" in i.page for i in stale)


def test_collect_gaps_window_filter(tmp_path):
    feedback = tmp_path / "feedback.md"
    feedback.write_text(
        "# feedback.md\n\n"
        "## [2026-05-19T10:00:00Z] query-gap | severity: hard\n"
        "Q: Recent question?\n"
        "No page covers this.\n\n"
        "## [2025-01-01T10:00:00Z] query-gap | severity: weak\n"
        "Q: Old question?\n"
        "Answered from a low page.\n",
        encoding="utf-8")
    gaps = lint.collect_gaps(feedback, 90, datetime.date(2026, 5, 20))
    assert len(gaps) == 1
    assert gaps[0]["severity"] == "hard"
    assert gaps[0]["lines"][0] == "Q: Recent question?"


def test_collect_gaps_missing_file(tmp_path):
    assert lint.collect_gaps(tmp_path / "nope.md", 90, datetime.date(2026, 5, 20)) == []


def test_write_report_sections(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "live.md").write_text(
        "---\ntitle: Live\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: low\n---\n\n"
        "Broken [[concepts/missing]].\n",
        encoding="utf-8")
    (wiki / "concepts" / "wip.md").write_text(
        "---\ntitle: WIP\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\ndraft: true\n---\n\n"
        "Broken [[concepts/alsomissing]].\n",
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    gaps = [{"ts": "2026-05-19T10:00:00Z", "severity": "hard",
             "lines": ["Q: Something?"]}]
    report = tmp_path / "lint-report.md"
    lint.write_report(report, issues, gaps, datetime.date(2026, 5, 20))
    txt = report.read_text(encoding="utf-8")
    assert "# Lint report" in txt
    assert "## Errors" in txt
    assert "## Warnings" in txt
    assert "low-confidence" in txt
    assert "## Draft pages" in txt
    assert "[[concepts/wip]]" in txt
    assert "## Open knowledge gaps" in txt
    assert "Q: Something?" in txt


def test_main_writes_report(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    wiki = workspace / "wiki"
    forge = workspace / ".forge"
    (wiki / "concepts").mkdir(parents=True)
    forge.mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        "---\ntitle: SGD\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lint", "--report",
                                     "--wiki", str(wiki),
                                     "--raw", str(workspace / "raw")])
    lint.main()
    assert (forge / "lint-report.md").exists()


def test_fix_regenerates_meta_index(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)
    (wiki / "concepts" / "sgd.md").write_text(
        _page("title: SGD\ntype: concept\ncreated: 2026-01-01\n"
              "last_verified: 2026-01-01\nconfidence: likely"),
        encoding="utf-8")
    lint.fix(wiki, datetime.date(2026, 5, 20))
    meta = wiki / ".meta"
    assert (meta / "pages.tsv").exists()
    assert (meta / "links.tsv").exists()
    assert "concepts/sgd" in (meta / "pages.tsv").read_text(encoding="utf-8")


def test_draft_page_error_is_non_blocking(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "wip.md").write_text(
        "---\ntitle: WIP\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\ndraft: true\n---\n\n"
        "A broken [[concepts/nonexistent]] link.\n",
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    broken = [i for i in issues if i.code == "broken-wikilink"]
    assert broken, "the broken wikilink should still be reported"
    assert broken[0].draft is True
    assert broken[0].is_blocking() is False
    assert not any(i.is_blocking() for i in issues)


def test_non_draft_page_error_is_blocking(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "live.md").write_text(
        "---\ntitle: Live\ntype: concept\ncreated: 2026-01-01\n"
        "last_verified: 2026-01-01\nconfidence: likely\n---\n\n"
        "A broken [[concepts/nonexistent]] link.\n",
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    assert any(i.is_blocking() for i in issues)


def test_low_confidence_warns(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "stub.md").write_text(
        _page("title: Stub\ntype: concept\ncreated: 2026-05-19\n"
              "last_verified: 2026-05-19\nconfidence: low"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    lc = [i for i in issues if i.code == "low-confidence"]
    assert lc and lc[0].severity == lint.WARNING


def test_fresh_placeholder_is_low_confidence_not_rotting(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "ph.md").write_text(
        _page("title: PH\ntype: concept\ncreated: 2026-05-19\n"
              "last_verified: 2026-05-19\nconfidence: placeholder"),
        encoding="utf-8")
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 5, 20))
    codes = {i.code for i in issues}
    assert "low-confidence" in codes
    assert "placeholder-rotting" not in codes
