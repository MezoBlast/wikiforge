import bootstrap


def test_create_credentials_file(tmp_path):
    (tmp_path / ".forge/secrets").mkdir(parents=True)
    rel = bootstrap.create_credentials_file(tmp_path)
    assert rel == ".forge/secrets/credentials.env"
    content = (tmp_path / rel).read_text()
    assert "MINERU_API_TOKEN" in content
    assert "TAVILY_API_KEY" in content
    assert content.lstrip().startswith("#")  # template is fully commented


def test_create_credentials_file_idempotent(tmp_path):
    (tmp_path / ".forge/secrets").mkdir(parents=True)
    assert bootstrap.create_credentials_file(tmp_path) == ".forge/secrets/credentials.env"
    assert bootstrap.create_credentials_file(tmp_path) is None


def test_create_credentials_file_creates_missing_dir(tmp_path):
    # .forge/secrets/ does not exist yet — the function must create it
    rel = bootstrap.create_credentials_file(tmp_path)
    assert (tmp_path / rel).is_file()
