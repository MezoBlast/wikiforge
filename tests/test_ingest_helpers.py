import pytest

import ingest_helpers as ih


def test_parse_queue_missing_file_returns_empty(tmp_path):
    assert list(ih.parse_queue(tmp_path / "nope.md")) == []


def test_append_queue_entry_creates_missing_file(tmp_path):
    q = tmp_path / "queue.md"
    created = ih.append_queue_entry(q, "raw/papers/a.pdf")
    assert created is True
    assert q.exists()
    assert q.read_text().startswith("# .forge/queue.md")
    entries = list(ih.parse_queue(q))
    assert len(entries) == 1
    assert entries[0][1] == " " and entries[0][2] == "raw/papers/a.pdf"


def test_set_queue_state_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ih.set_queue_state(tmp_path / "nope.md", "raw/x", "x")


def test_scan_raw_finds_files_and_repos(tmp_path):
    (tmp_path / "raw/papers").mkdir(parents=True)
    (tmp_path / "raw/papers/a.pdf").write_bytes(b"%PDF fake")
    (tmp_path / "raw/papers/.gitkeep").write_text("")
    (tmp_path / "raw/notes").mkdir(parents=True)
    (tmp_path / "raw/notes/n.md").write_text("note")
    (tmp_path / "raw/web").mkdir(parents=True)
    (tmp_path / "raw/web/page.html").write_text("<h1>x</h1>")
    repo = tmp_path / "raw/repos/acme/widget@abc123"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("readme")
    # a .converted output directory must be excluded entirely
    conv = tmp_path / "raw/papers/a.converted"
    conv.mkdir()
    (conv / "a.md").write_text("converted")

    found = {str(p) for p in ih.scan_raw(tmp_path)}

    assert str(tmp_path / "raw/papers/a.pdf") in found
    assert str(tmp_path / "raw/notes/n.md") in found
    assert str(tmp_path / "raw/web/page.html") in found
    assert str(repo) in found
    assert not any(".converted" in f for f in found)
    assert not any(".gitkeep" in f for f in found)
    # the repo's inner files are NOT yielded individually
    assert str(repo / "README.md") not in found


def _write_source_page(dir_path, name, content_hash, source_path):
    page = dir_path / name
    page.write_text(
        "---\n"
        f"title: {name}\n"
        "type: source\n"
        "created: 2026-01-01\n"
        "last_verified: 2026-01-01\n"
        "confidence: likely\n"
        "source_type: paper\n"
        f"source_path: {source_path}\n"
        f"content_hash: {content_hash}\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )


def test_find_ingested_source_by_hash(tmp_path):
    src = tmp_path / "wiki/sources"
    src.mkdir(parents=True)
    _write_source_page(src, "foo.md", "sha256:abc123", "raw/papers/foo.pdf")
    hit = ih.find_ingested_source(tmp_path, content_hash="sha256:abc123")
    assert hit is not None
    slug, fm = hit
    assert slug == "sources/foo"
    assert fm["source_path"] == "raw/papers/foo.pdf"
    assert ih.find_ingested_source(tmp_path, content_hash="sha256:zzz") is None


def test_find_ingested_source_by_path(tmp_path):
    src = tmp_path / "wiki/sources"
    src.mkdir(parents=True)
    _write_source_page(src, "foo.md", "sha256:abc123", "raw/papers/foo.pdf")
    hit = ih.find_ingested_source(tmp_path, source_path="raw/papers/foo.pdf")
    assert hit is not None and hit[0] == "sources/foo"


def test_find_ingested_source_missing_dir(tmp_path):
    assert ih.find_ingested_source(tmp_path, content_hash="sha256:abc") is None


def test_find_ingested_source_requires_a_key(tmp_path):
    with pytest.raises(ValueError):
        ih.find_ingested_source(tmp_path)
