import os

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
