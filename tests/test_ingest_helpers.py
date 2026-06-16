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


def test_queue_handles_path_with_spaces(tmp_path):
    q = tmp_path / "queue.md"
    spaced = "raw/web/Tuna-2_ Pixel Embeddings Beat Vision Encoders.html"
    ih.append_queue_entry(q, spaced)
    entries = list(ih.parse_queue(q))
    assert len(entries) == 1
    assert entries[0][2] == spaced
    assert entries[0][3] == ""  # the spaces are not mis-parsed as a note
    ih.set_queue_state(q, spaced, "x")
    assert list(ih.parse_queue(q))[0][1] == "x"


def test_queue_spaced_path_keeps_note_separate(tmp_path):
    q = tmp_path / "queue.md"
    spaced = "raw/web/a b c.html"
    ih.append_queue_entry(q, spaced, note="req 2026-05-20-001")
    _, state, path, note = list(ih.parse_queue(q))[0]
    assert path == spaced and note == "req 2026-05-20-001"


def test_content_hash_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    h = ih.content_hash(f)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 16
    assert ih.content_hash(f) == h  # deterministic


def test_content_hash_directory_is_deterministic(tmp_path):
    repo = tmp_path / "org" / "repo@abc123"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("readme")
    (repo / "src" / "main.py").write_text("print(1)")
    h1 = ih.content_hash(repo)
    h2 = ih.content_hash(repo)
    assert h1 == h2 and h1.startswith("sha256:")


def test_content_hash_directory_differs_from_other_dir(tmp_path):
    a = tmp_path / "a@1"
    b = tmp_path / "b@1"
    a.mkdir()
    b.mkdir()
    (a / "f.txt").write_text("one")
    (b / "f.txt").write_text("a much longer file body")
    assert ih.content_hash(a) != ih.content_hash(b)


def test_content_hash_directory_ignores_git(tmp_path):
    repo = tmp_path / "repo@abc"
    repo.mkdir()
    (repo / "README.md").write_text("x")
    before = ih.content_hash(repo)
    gitdir = repo / ".git"
    gitdir.mkdir()
    (gitdir / "HEAD").write_text("ref: refs/heads/main")
    assert ih.content_hash(repo) == before  # .git changes don't affect the hash


def _make_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)
    return wiki


def test_create_placeholder_stub_concept(tmp_path):
    _make_wiki(tmp_path)
    slug = ih.create_placeholder_stub(
        "concepts/clip-score", "CLIPScore",
        gloss="embedding-based text-image alignment metric.",
        linked_from="[[concepts/mllm-as-a-judge]] as a baseline",
        workspace_root=tmp_path,
    )
    assert slug == "concepts/clip-score"
    text = (tmp_path / "wiki/concepts/clip-score.md").read_text()
    assert "confidence: placeholder" in text
    assert "- stub" in text  # tags rendered as a yaml block list
    assert "**What it is:** embedding-based text-image alignment metric." in text
    assert "**Linked from:** [[concepts/mllm-as-a-judge]] as a baseline" in text
    assert "Expected scope" not in text  # omitted when arg absent
    assert "Source hint" not in text


def test_create_placeholder_stub_entity_ok(tmp_path):
    _make_wiki(tmp_path)
    ih.create_placeholder_stub(
        "entities/clip", "CLIP",
        gloss="vision-language model.",
        linked_from="[[concepts/clip-score]]",
        entity_type="tool",
        expected_scope="architecture and training.",
        source_hint="Radford et al. 2021",
        aliases=["Contrastive Language-Image Pretraining"],
        workspace_root=tmp_path,
    )
    text = (tmp_path / "wiki/entities/clip.md").read_text()
    assert "type: entity" in text
    assert "entity_type: tool" in text
    assert "**Expected scope:** architecture and training." in text
    assert "**Source hint:** Radford et al. 2021" in text
    assert "Contrastive Language-Image Pretraining" in text


def test_create_placeholder_stub_entity_requires_entity_type(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub(
            "entities/q-judger", "Q-Judger",
            gloss="a judge model.", linked_from="[[sources/x]]",
            workspace_root=tmp_path,
        )


def test_create_placeholder_stub_entity_rejects_bad_type(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError, match="invalid entity_type"):
        ih.create_placeholder_stub(
            "entities/x", "X",
            gloss="a thing.", linked_from="[[concepts/a]]",
            entity_type="model",  # not in ENTITY_TYPE
            workspace_root=tmp_path,
        )


def test_create_placeholder_stub_rejects_claim(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub(
            "claims/foo", "Foo", gloss="x.", linked_from="[[sources/y]]",
            workspace_root=tmp_path,
        )


def test_create_placeholder_stub_requires_gloss_and_linked_from(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub("concepts/a", "A", gloss="  ",
                                   linked_from="[[x]]", workspace_root=tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub("concepts/a", "A", gloss="ok.",
                                   linked_from="", workspace_root=tmp_path)


def test_create_placeholder_stub_idempotent(tmp_path):
    _make_wiki(tmp_path)
    kw = dict(gloss="x.", linked_from="[[concepts/a]]", workspace_root=tmp_path)
    first = ih.create_placeholder_stub("concepts/dup", "Dup", **kw)
    (tmp_path / "wiki/concepts/dup.md").write_text("SENTINEL", encoding="utf-8")
    second = ih.create_placeholder_stub("concepts/dup", "Dup", **kw)
    assert first == "concepts/dup"
    assert second is None
    assert (tmp_path / "wiki/concepts/dup.md").read_text() == "SENTINEL"


def test_create_placeholder_stub_lints_clean(tmp_path):
    import datetime
    import lint
    wiki = _make_wiki(tmp_path)
    (wiki / "concepts/a.md").write_text(
        "---\ntitle: A\ntype: concept\ncreated: '2026-01-01'\n"
        "last_verified: '2026-01-01'\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    ih.create_placeholder_stub(
        "entities/clip", "CLIP", gloss="vlm.",
        linked_from="[[concepts/a]]", entity_type="tool",
        workspace_root=tmp_path)
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 6, 16))
    errors = [i for i in issues if i.severity == lint.ERROR]
    assert errors == []  # placeholder warnings are fine; zero errors
