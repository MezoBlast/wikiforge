"""Unit tests for build.validate_no_dangling_refs."""
import pytest

import build


def _page(slug, page_type, body, **fm):
    """Helper: synthesize a (slug, page_type, fm, body) tuple."""
    fm.setdefault("title", slug.rsplit("/", 1)[-1])
    return (slug, page_type, fm, body)


def test_clean_pages_set_does_not_raise():
    pages = [
        _page("concepts/a", "concept", "See [[concepts/b]] for context."),
        _page("concepts/b", "concept", "A standalone page."),
    ]
    kept_slugs = {"concepts/a", "concepts/b"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise


def test_dangling_prose_link_raises_systemexit(capsys):
    pages = [
        _page("concepts/a", "concept", "See [[concepts/missing]] for context."),
    ]
    kept_slugs = {"concepts/a"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    assert "concepts/a" in err
    assert "body" in err
    assert "[[concepts/missing]]" in err
    assert "1 dangling reference" in str(excinfo.value)


def test_wikilink_inside_html_comment_is_ignored():
    pages = [
        _page("concepts/a", "concept", "Body. <!-- TODO [[concepts/missing]] --> end."),
    ]
    kept_slugs = {"concepts/a"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise


def test_dangling_typed_edge_raises_systemexit(capsys):
    pages = [
        _page(
            "claims/a",
            "claim",
            "A claim body.",
            supersedes=["claims/missing"],
        ),
    ]
    kept_slugs = {"claims/a"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    assert "claims/a" in err
    assert "frontmatter:supersedes" in err
    assert "[[claims/missing]]" in err
    assert "1 dangling reference" in str(excinfo.value)


def test_basename_shorthand_resolves():
    """A prose link `[[sgd]]` resolves to `concepts/sgd` if that's the only match."""
    pages = [
        _page("concepts/a", "concept", "See [[sgd]] for context."),
        _page("concepts/sgd", "concept", "SGD page body."),
    ]
    kept_slugs = {"concepts/a", "concepts/sgd"}
    build.validate_no_dangling_refs(pages, kept_slugs)  # must not raise


def test_reports_all_failures_in_sorted_order(capsys):
    pages = [
        _page(
            "z-page",
            "concept",
            "[[missing-c]] and [[missing-a]] and [[missing-b]].",
        ),
        _page("a-page", "concept", "[[missing-z]]."),
    ]
    kept_slugs = {"z-page", "a-page"}
    with pytest.raises(SystemExit) as excinfo:
        build.validate_no_dangling_refs(pages, kept_slugs)
    err = capsys.readouterr().err
    lines = [l for l in err.splitlines() if l.startswith("dangling-ref:")]
    assert len(lines) == 4
    # Sorted by (from_slug, source, target):
    assert "a-page" in lines[0] and "[[missing-z]]" in lines[0]
    assert "z-page" in lines[1] and "[[missing-a]]" in lines[1]
    assert "z-page" in lines[2] and "[[missing-b]]" in lines[2]
    assert "z-page" in lines[3] and "[[missing-c]]" in lines[3]
    assert "4 dangling reference" in str(excinfo.value)
