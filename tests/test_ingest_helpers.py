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
