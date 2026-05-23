from pathlib import Path

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


import subprocess


def test_pdf_routes_to_mineru(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "doc.md").write_text("# Converted by MinerU")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(pdf)
    assert out == tmp_path / "doc.converted" / "doc.md"
    assert out.read_text() == "# Converted by MinerU"
    assert any("mineru_api.py" in str(part) for part in calls[0])


def test_pdf_failure_raises_normalize_error(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF fake")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "File too large (12.0MB > 10MB).")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="MinerU"):
        normalize.normalize_source(pdf)


def test_docx_also_routes_to_mineru(tmp_path, monkeypatch):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK fake docx")

    def fake_run(cmd, **kwargs):
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.md").write_text("# Report")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(docx)
    assert out.read_text() == "# Report"


def test_url_routes_to_tvly(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com/article\n")

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "tvly" and cmd[1] == "extract"
        assert cmd[2] == "https://example.com/article"
        out = Path(cmd[cmd.index("-o") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# Extracted article")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    out = normalize.normalize_source(src)
    assert out == tmp_path / "article.converted" / "article.md"
    assert out.read_text() == "# Extracted article"


def test_url_failure_raises_normalize_error(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 3, "", "auth error")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="tvly"):
        normalize.normalize_source(src)


def test_url_empty_file_raises(tmp_path):
    src = tmp_path / "article.url"
    src.write_text("   \n")
    with pytest.raises(normalize.NormalizeError, match="no URL"):
        normalize.normalize_source(src)


def test_url_missing_cli_raises(tmp_path, monkeypatch):
    src = tmp_path / "article.url"
    src.write_text("https://example.com\n")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("tvly")

    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    with pytest.raises(normalize.NormalizeError, match="Tavily CLI"):
        normalize.normalize_source(src)


def test_agent_extract_advice_pdf_oversize_no_token(tmp_path, monkeypatch):
    p = tmp_path / "big.pdf"
    p.write_bytes(b"x" * (11 * 1024 * 1024))   # 11 MB > 10 MB
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "10 MB" in reason
    assert "MINERU_API_TOKEN" in reason


def test_agent_extract_advice_pdf_small_no_token(tmp_path, monkeypatch):
    p = tmp_path / "small.pdf"
    p.write_bytes(b"x" * 1024)
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "MINERU_API_TOKEN" in reason


def test_agent_extract_advice_pdf_token_present(tmp_path, monkeypatch):
    p = tmp_path / "p.pdf"
    p.write_bytes(b"x" * 1024)
    monkeypatch.setattr(normalize, "load_credentials",
                        lambda **kw: {"MINERU_API_TOKEN": "tok123"})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is True
    assert mechanism == "pdf-read"
    assert "token" in reason.lower()


def test_agent_extract_advice_docx(tmp_path, monkeypatch):
    p = tmp_path / "f.docx"
    p.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_pptx(tmp_path, monkeypatch):
    p = tmp_path / "f.pptx"
    p.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_xlsx(tmp_path, monkeypatch):
    p = tmp_path / "f.xlsx"
    p.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "unzip-officex")


def test_agent_extract_advice_html(tmp_path, monkeypatch):
    p = tmp_path / "page.html"
    p.write_text("<p>hi</p>")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "html-text")


def test_agent_extract_advice_htm(tmp_path, monkeypatch):
    p = tmp_path / "page.htm"
    p.write_text("<p>hi</p>")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (True, "html-text")


def test_agent_extract_advice_xls(tmp_path, monkeypatch):
    p = tmp_path / "f.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert ("ole" in reason.lower()) or ("legacy" in reason.lower())


def test_agent_extract_advice_url(tmp_path, monkeypatch):
    p = tmp_path / "x.url"
    p.write_text("https://example.com\n")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert ("tavily" in reason.lower()) or ("fetch" in reason.lower())


def test_agent_extract_advice_weblink(tmp_path, monkeypatch):
    p = tmp_path / "x.weblink"
    p.write_text("https://example.com\n")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, _ = normalize.agent_extract_advice(p)
    assert (eligible, mechanism) == (False, "none")


def test_agent_extract_advice_unknown_extension(tmp_path, monkeypatch):
    p = tmp_path / "thing.xyz"
    p.write_text("data")
    monkeypatch.setattr(normalize, "load_credentials", lambda **kw: {})
    eligible, mechanism, reason = normalize.agent_extract_advice(p)
    assert eligible is False
    assert mechanism == "none"
    assert "no normalizer" in reason.lower()
