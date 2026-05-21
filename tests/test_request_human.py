import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _make_workspace(tmp_path):
    skill = tmp_path / ".forge/skills/request-human"
    skill.mkdir(parents=True)
    shutil.copy2(REPO / ".forge/skills/request-human/submit.sh", skill / "submit.sh")
    (skill / "submit.sh").chmod(0o755)
    (tmp_path / ".forge/requests/inbox").mkdir(parents=True)
    (tmp_path / ".forge/requests/responses").mkdir(parents=True)
    (tmp_path / ".forge/log.md").write_text("# .forge/log.md\n")
    return tmp_path


def test_submit_logs_real_timestamp(tmp_path):
    ws = _make_workspace(tmp_path)
    before = datetime.now(timezone.utc)
    r = subprocess.run(
        [str(ws / ".forge/skills/request-human/submit.sh"),
         "--agent", "ingest", "--type", "test-type", "--urgency", "useful",
         "--title", "T"],
        input="## What I need\nx\n", capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    log = (ws / ".forge/log.md").read_text()
    m = re.search(r"## \[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\] request-human", log)
    assert m, log
    ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs((ts - before).total_seconds()) < 120
