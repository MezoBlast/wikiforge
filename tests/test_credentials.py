import os
from pathlib import Path

import credentials


def test_parse_env_basic():
    assert credentials.parse_env("A=1\nB=two\n") == {"A": "1", "B": "two"}


def test_parse_env_ignores_comments_and_blanks():
    assert credentials.parse_env("# c\n\nA=1\n   # indented\nB=2\n") == {"A": "1", "B": "2"}


def test_parse_env_value_keeps_inner_equals():
    assert credentials.parse_env("K=a=b=c")["K"] == "a=b=c"


def test_parse_env_strips_whitespace():
    assert credentials.parse_env("  A = 1  \n") == {"A": "1"}


def test_load_credentials_missing_file(tmp_path):
    assert credentials.load_credentials(tmp_path / "nope.env") == {}


def test_load_credentials_into_environ(tmp_path, monkeypatch):
    f = tmp_path / "c.env"
    f.write_text("WF_TEST_TOKEN=xyz\n")
    monkeypatch.delenv("WF_TEST_TOKEN", raising=False)
    result = credentials.load_credentials(f, into_environ=True)
    assert result == {"WF_TEST_TOKEN": "xyz"}
    assert os.environ["WF_TEST_TOKEN"] == "xyz"


def test_load_credentials_real_env_wins(tmp_path, monkeypatch):
    f = tmp_path / "c.env"
    f.write_text("WF_TEST_TOKEN=fromfile\n")
    monkeypatch.setenv("WF_TEST_TOKEN", "fromenv")
    credentials.load_credentials(f, into_environ=True)
    assert os.environ["WF_TEST_TOKEN"] == "fromenv"


def test_default_path_is_absolute():
    # DEFAULT_PATH must not be a cwd-relative string — a skill running Python
    # from inside .forge/lib/ would otherwise resolve it wrong and drop the token.
    assert Path(credentials.DEFAULT_PATH).is_absolute()


def test_default_path_points_at_workspace_secrets():
    p = Path(credentials.DEFAULT_PATH)
    assert p.parts[-3:] == (".forge", "secrets", "credentials.env")
    # credentials.py lives at <root>/.forge/lib/credentials.py;
    # the default must resolve to <root>/.forge/secrets/credentials.env
    root = Path(credentials.__file__).resolve().parents[2]
    assert p == root / ".forge" / "secrets" / "credentials.env"


import stat

import pytest


def test_set_credential_uncomments_commented_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# MINERU_API_TOKEN=\n# TAVILY_API_KEY=\n")
    credentials.set_credential("MINERU_API_TOKEN", "abc123", path=f)
    text = f.read_text()
    assert "MINERU_API_TOKEN=abc123\n" in text
    # The OTHER commented line is preserved exactly.
    assert "# TAVILY_API_KEY=\n" in text


def test_set_credential_updates_existing_uncommented_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("MINERU_API_TOKEN=old\n")
    credentials.set_credential("MINERU_API_TOKEN", "new", path=f)
    assert f.read_text() == "MINERU_API_TOKEN=new\n"


def test_set_credential_appends_new_key(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("OTHER=foo\n")
    credentials.set_credential("NEW_KEY", "bar", path=f)
    text = f.read_text()
    assert "OTHER=foo\n" in text
    assert "NEW_KEY=bar\n" in text


def test_set_credential_preserves_other_lines(tmp_path):
    f = tmp_path / "c.env"
    seed = "# header comment\n\nFIRST=1\n# commented note\nSECOND=2\n"
    f.write_text(seed)
    credentials.set_credential("SECOND", "two", path=f)
    text = f.read_text()
    assert "# header comment\n" in text
    assert "\n\n" in text             # blank line preserved
    assert "FIRST=1\n" in text
    assert "# commented note\n" in text
    assert "SECOND=two\n" in text
    assert "SECOND=2\n" not in text   # old value gone


def test_set_credential_empty_value_rejected(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    with pytest.raises(ValueError):
        credentials.set_credential("K", "", path=f)


def test_set_credential_whitespace_value_rejected(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    with pytest.raises(ValueError):
        credentials.set_credential("K", "   ", path=f)


def test_set_credential_creates_file_with_secure_mode(tmp_path):
    f = tmp_path / "fresh.env"
    assert not f.exists()
    credentials.set_credential("K", "v", path=f)
    assert f.read_text() == "K=v\n"
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o600


def test_set_credential_does_not_change_existing_file_mode(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("# K=\n")
    os.chmod(f, 0o644)
    credentials.set_credential("K", "v", path=f)
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o644
