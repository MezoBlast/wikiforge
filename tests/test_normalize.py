import pytest

import normalize


def test_converted_dir_naming():
    d = normalize.converted_dir("raw/papers/foo.pdf")
    assert d.name == "foo.converted"
    assert str(d) == "raw/papers/foo.converted"


def test_plaintext_returns_original(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("# hi")
    assert normalize.normalize_source(note) == note


def test_directory_returns_itself(tmp_path):
    repo = tmp_path / "acme/widget@abc"
    repo.mkdir(parents=True)
    assert normalize.normalize_source(repo) == repo


def test_missing_source_raises(tmp_path):
    with pytest.raises(normalize.NormalizeError):
        normalize.normalize_source(tmp_path / "nope.pdf")


def test_unknown_extension_raises(tmp_path):
    weird = tmp_path / "thing.xyz"
    weird.write_text("data")
    with pytest.raises(normalize.NormalizeError, match="no normalizer"):
        normalize.normalize_source(weird)


def test_html_conversion(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>Title</h1><p>Body text here.</p>")
    out = normalize.normalize_source(page)
    assert out == tmp_path / "page.converted" / "page.md"
    text = out.read_text()
    assert "Title" in text and "Body text here." in text
    assert page.exists()  # original untouched


def test_html_conversion_idempotent(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>X</h1>")
    first = normalize.normalize_source(page)
    first.write_text("EDITED — should be reused, not regenerated")
    second = normalize.normalize_source(page)
    assert second == first
    assert second.read_text().startswith("EDITED")


def test_html_force_reconverts(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<h1>X</h1>")
    first = normalize.normalize_source(page)
    first.write_text("STALE")
    second = normalize.normalize_source(page, force=True)
    assert "STALE" not in second.read_text()
    assert "X" in second.read_text()
