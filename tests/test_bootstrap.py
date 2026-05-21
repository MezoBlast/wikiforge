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


def test_seed_files_include_feedback(tmp_path):
    created = bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    assert ".forge/feedback.md" in created
    content = (tmp_path / ".forge/feedback.md").read_text()
    assert content.startswith("# .forge/feedback.md")


def test_seed_feedback_idempotent(tmp_path):
    bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    again = bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    assert ".forge/feedback.md" not in again  # already exists, not re-created


import re
from datetime import datetime, timezone


def test_forge_log_seed_has_real_timestamp(tmp_path):
    before = datetime.now(timezone.utc)
    bootstrap.create_seed_files(tmp_path, "2026-05-20", "test-domain")
    content = (tmp_path / ".forge/log.md").read_text()
    m = re.search(r"## \[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\] bootstrap", content)
    assert m, content
    ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs((ts - before).total_seconds()) < 120  # a real wall-clock time
