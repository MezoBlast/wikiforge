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
