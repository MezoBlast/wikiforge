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
