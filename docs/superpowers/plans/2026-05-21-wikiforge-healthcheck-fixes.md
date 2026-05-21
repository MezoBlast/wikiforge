# WikiForge Health-Check Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven framework defects surfaced by the multimodal-llm pipeline integration test.

**Architecture:** All changes land on branch `fix/healthcheck-2026-05-21` (off `master`). Python helpers in `.forge/lib/` are unit-tested with pytest (`tests/conftest.py` already puts `.forge/lib/` on `sys.path`). The POSIX shell scripts in `bin/` and `.forge/skills/` are tested via `subprocess` against temp-dir fixtures. SKILL.md / runbook edits are documentation and are verified by diff review plus the final integration task.

**Tech Stack:** Python 3 (system `python3` — it has `pyyaml`; do **not** use `.venv`), pytest, POSIX `sh` + `awk` + `grep`.

**Spec:** `docs/superpowers/specs/2026-05-21-wikiforge-healthcheck-fixes-design.md`

---

## Task 1: Fix 2 — cwd-robust credential loading

`.forge/lib/credentials.py` defines `DEFAULT_PATH` as a bare relative string. When a skill runs Python with its working directory inside `.forge/lib/`, `load_credentials()` resolves the path wrong, finds nothing, and silently drops `MINERU_API_TOKEN`. Anchor the default to the module's own location.

**Files:**
- Modify: `.forge/lib/credentials.py:14` (the `DEFAULT_PATH` definition)
- Test: `tests/test_credentials.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_credentials.py`:

```python
from pathlib import Path


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_credentials.py -v`
Expected: `test_default_path_is_absolute` FAILS (a relative string is not absolute).

- [ ] **Step 3: Make `DEFAULT_PATH` `__file__`-anchored**

In `.forge/lib/credentials.py`, replace line 14:

```python
DEFAULT_PATH = ".forge/secrets/credentials.env"
```

with:

```python
DEFAULT_PATH = Path(__file__).resolve().parents[2] / ".forge" / "secrets" / "credentials.env"
```

`Path` is already imported (line 12). `credentials.py` lives at `<root>/.forge/lib/credentials.py`, so `parents[2]` is the workspace root. The `load_credentials(path=DEFAULT_PATH, ...)` signature is unchanged — callers passing an explicit `path` (including the existing tests) are unaffected; only the no-argument default changes from cwd-relative to absolute.

- [ ] **Step 4: Run the full credentials test file to verify all pass**

Run: `python3 -m pytest tests/test_credentials.py -v`
Expected: PASS — the two new tests plus all six pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add .forge/lib/credentials.py tests/test_credentials.py
git commit -m "fix: anchor credentials DEFAULT_PATH to module location, not cwd"
```

---

## Task 2: Fix 1 — `bin/wiki-search` OR-match + ranked retrieval

`bin/wiki-search` matches the whole query as one contiguous string (`grep -i -- "$q"`), so natural-language phrases almost never match. Replace it with per-term OR matching ranked by matched-term count.

**Files:**
- Modify: `bin/wiki-search` (full rewrite)
- Test: `tests/test_wiki_search.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_wiki_search.py`:

```python
import os
import subprocess
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin" / "wiki-search"


def _make_wiki(root):
    meta = root / "wiki" / ".meta"
    meta.mkdir(parents=True)
    (meta / "pages.tsv").write_text(
        "path\ttitle\ttype\ttags\tlast_verified\tconfidence\n"
        "concepts/vision-language-fusion\tVision-language fusion strategies\t"
        "concept\tfusion,vision-encoder\t2026-05-21\tlow\n"
        "code-patterns/siglip-projector\tMLP projector connecting a SigLIP encoder to an LLM\t"
        "code-pattern\tprojector,siglip\t2026-05-21\tlikely\n"
    )
    c = root / "wiki" / "concepts"
    c.mkdir(parents=True)
    (c / "vision-language-fusion.md").write_text(
        "# Vision-language fusion strategies\n\n"
        "Canonical strategies for fusing a vision encoder with a language model.\n"
    )
    cp = root / "wiki" / "code-patterns"
    cp.mkdir(parents=True)
    (cp / "siglip-projector.md").write_text(
        "# MLP projector\n\n"
        "Connect a frozen vision encoder to an LLM through a projector.\n"
    )


def _search(root, *args):
    return subprocess.run(
        [str(BIN), *args],
        env={**os.environ, "WIKI_ROOT": str(root)},
        capture_output=True, text=True,
    )


def test_multiword_natural_language_query_matches(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "fusing a vision encoder with a language model")
    assert r.returncode == 0, r.stderr
    assert "concepts/vision-language-fusion" in r.stdout


def test_term_order_does_not_matter(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "projector encoder vision")
    assert "code-patterns/siglip-projector" in r.stdout


def test_type_filter_still_works(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "--type", "concept", "projector vision encoder")
    assert "concepts/vision-language-fusion" in r.stdout
    assert "code-patterns/siglip-projector" not in r.stdout


def test_ranking_prefers_more_matched_terms(tmp_path):
    _make_wiki(tmp_path)
    r = _search(tmp_path, "vision encoder projector llm")
    hits = [ln for ln in r.stdout.splitlines() if ln.startswith("[score")]
    assert hits, r.stdout
    # the projector page matches projector+encoder+llm; fusion page matches fewer
    assert "code-patterns/siglip-projector" in hits[0]


def test_missing_index_errors(tmp_path):
    r = _search(tmp_path, "anything")
    assert r.returncode == 1
    assert "no" in r.stderr.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_wiki_search.py -v`
Expected: `test_multiword_natural_language_query_matches` and `test_term_order_does_not_matter` FAIL — the current script does contiguous-phrase matching.

- [ ] **Step 3: Rewrite `bin/wiki-search`**

Replace the entire contents of `bin/wiki-search` with:

```sh
#!/bin/sh
# wiki-search — OR-match query terms; rank by matched-term count + title/phrase bonus
set -eu
type=""; n=10
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) echo "usage: wiki-search [--type T] [--n N] <query>"; exit 0 ;;
        --type) type="${2:?--type requires value}"; shift 2 ;;
        --n)    n="${2:?--n requires value}"; shift 2 ;;
        --) shift; break ;;
        -*) echo "wiki-search: unknown argument: $1" >&2; exit 2 ;;
        *)  break ;;
    esac
done
q="$*"
[ -n "$q" ] || { echo "wiki-search: query required" >&2; exit 2; }
WIKI_ROOT="${WIKI_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
wiki="$WIKI_ROOT/wiki"
meta="$wiki/.meta/pages.tsv"
[ -f "$meta" ] || { echo "wiki-search: no $meta — run the build" >&2; exit 1; }
tab=$(printf '\t')

qlc=$(printf '%s' "$q" | tr '[:upper:]' '[:lower:]')

# stop-words dropped from the term list (surrounding spaces make matching exact)
stop=" a an and are as at be by for from has in is it its of on or that the to with "

# tokenize: lowercase words, strip punctuation, drop stop-words and tokens <=2 chars
tokens=""
for w in $qlc; do
    w=$(printf '%s' "$w" | tr -cd 'a-z0-9-')
    [ "${#w}" -gt 2 ] || continue
    case "$stop" in *" $w "*) continue ;; esac
    tokens="$tokens $w"
done
# degenerate query (all stop-words / short): fall back to the raw words
if [ -z "${tokens# }" ]; then
    for w in $qlc; do
        w=$(printf '%s' "$w" | tr -cd 'a-z0-9-')
        [ -n "$w" ] && tokens="$tokens $w"
    done
fi

# score each indexed page: title/tag/slug/body term hits + whole-phrase bonus
awk -F'\t' 'NR==1 && $1=="path" {next} {print}' "$meta" \
| while IFS="$tab" read -r path title ptype tags rest; do
    [ -n "$type" ] && [ "$ptype" != "$type" ] && continue
    file="$wiki/$path.md"
    tlc=$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]')
    glc=$(printf '%s' "$tags"  | tr '[:upper:]' '[:lower:]')
    plc=$(printf '%s' "$path"  | tr '[:upper:]' '[:lower:]')
    score=0; matched=0
    case "$tlc" in *"$qlc"*) score=$((score + 100)) ;; esac
    if [ -f "$file" ] && grep -F -i -q -- "$q" "$file" 2>/dev/null; then
        score=$((score + 40))
    fi
    for tok in $tokens; do
        hit=0
        case "$tlc" in *"$tok"*) score=$((score + 10)); hit=1 ;; esac
        case "$glc" in *"$tok"*) score=$((score + 5));  hit=1 ;; esac
        case "$plc" in *"$tok"*) score=$((score + 8));  hit=1 ;; esac
        if [ -f "$file" ] && grep -F -i -q -- "$tok" "$file" 2>/dev/null; then
            score=$((score + 1)); hit=1
        fi
        [ "$hit" -eq 1 ] && matched=$((matched + 1))
    done
    [ "$matched" -gt 0 ] || continue
    snip=""
    if [ -f "$file" ]; then
        for tok in $tokens; do
            snip=$(grep -i -m1 -F -- "$tok" "$file" 2>/dev/null | cut -c1-160 | tr '\t' ' ')
            [ -n "$snip" ] && break
        done
    fi
    printf '%s\t%s\t%s\n' "$score" "$path" "$snip"
done \
| sort -t "$tab" -k1,1nr -k2,2 \
| awk -F'\t' '!seen[$2]++' \
| head -n "$n" \
| awk -F'\t' '{ printf "[score %s] %s\n  %s\n", $1, $2, $3 }'
```

- [ ] **Step 4: Make the script executable and run the tests**

Run: `chmod +x bin/wiki-search && python3 -m pytest tests/test_wiki_search.py -v`
Expected: PASS — all five tests.

- [ ] **Step 5: Verify no regression in the other bin scripts**

Run: `sh -n bin/wiki-search && echo "syntax ok"`
Expected: `syntax ok` (POSIX syntax check passes).

- [ ] **Step 6: Commit**

```bash
git add bin/wiki-search tests/test_wiki_search.py
git commit -m "fix: wiki-search OR-matches query terms and ranks by hit count"
```

---

## Task 3: Fix 1 — update `query/SKILL.md` for OR+ranked search

The query skill must tell the agent to extract keywords (not pass the raw question), and the worked examples must reflect the new `[score N]` output.

**Files:**
- Modify: `.forge/skills/query/SKILL.md` (Section 2 and both worked examples)

- [ ] **Step 1: Replace Section 2 ("Search")**

Replace lines 47–63 of `.forge/skills/query/SKILL.md` (the entire `### 2. Search` section, from the `### 2. Search` heading through the `bin/wiki-list --tag optimization` code block) with:

````markdown
### 2. Search

Turn the question into search terms — do not pass the raw question.
`bin/wiki-search` matches **each term independently** (case-insensitive) and
ranks pages by how many distinct terms hit, weighting title, tag, and slug
matches above body matches. You do not need the wiki's exact phrasing: pull
3–6 salient keywords out of the question and pass those.

```sh
bin/wiki-search <keyword keyword keyword>
bin/wiki-search --type claim <keywords>     # narrow to one page type
```

`--type` accepts any of the six page types: `concept`, `convention`,
`code-pattern`, `claim`, `source`, `entity`. Each result is a `[score N]
<slug>` line followed by a snippet; a higher score means more terms matched.
`--n N` caps the count (default 10). If the top results look off, try a
different keyword set — broader or more specific — rather than reaching for the
question's exact wording.

To browse rather than search:

```sh
bin/wiki-list --type concept             # every concept page
bin/wiki-list --tag optimization         # every page carrying a tag
```
````

- [ ] **Step 2: Fix the answerable worked example output**

In `.forge/skills/query/SKILL.md`, in the "Worked example — an answerable question" section, replace these two comment lines:

```sh
#   [1] concepts/optimization/adagrad (title)
#   [3] concepts/optimization/sgd (body)
```

with:

```sh
#   [score 123] concepts/optimization/adagrad
#   [score 11]  concepts/optimization/sgd
```

- [ ] **Step 3: Verify the hard-gap example still reads correctly**

Read the "Worked example — a hard gap" section. The `bin/wiki-search lion optimizer # no results` lines need no change — a no-match query still produces no output. Confirm by reading; make no edit.

- [ ] **Step 4: Review the diff**

Run: `git diff .forge/skills/query/SKILL.md`
Expected: only Section 2 and the two example-output lines changed; no other sections touched.

- [ ] **Step 5: Commit**

```bash
git add .forge/skills/query/SKILL.md
git commit -m "docs: query skill instructs keyword extraction for OR-ranked search"
```

---

## Task 4: Fix 5 — real timestamps in the operation log

`bootstrap.py` and `request-human/submit.sh` both write `.forge/log.md` entries with a hardcoded `T00:00:00Z` time. Replace with a real UTC timestamp.

**Files:**
- Modify: `.forge/lib/bootstrap.py` (the `.forge/log.md` entry in `SEED_FILES` ~line 188; `create_seed_files` ~line 198)
- Modify: `.forge/skills/request-human/submit.sh:58` and `:100-101`
- Test: `tests/test_bootstrap.py`, `tests/test_request_human.py` (create)

- [ ] **Step 1: Write the failing bootstrap test**

Append to `tests/test_bootstrap.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_bootstrap.py::test_forge_log_seed_has_real_timestamp -v`
Expected: FAIL — the seeded line is `<today>T00:00:00Z`, which is not within 120s of now.

- [ ] **Step 3: Fix `bootstrap.py`**

In `.forge/lib/bootstrap.py`, in the `SEED_FILES` dict, change the `.forge/log.md` entry from:

```python
    ".forge/log.md": (
        "# .forge/log.md — append-only curator-side operation log\n"
        "\n"
        "## [{today}T00:00:00Z] bootstrap | workspace created\n"
    ),
```

to:

```python
    ".forge/log.md": (
        "# .forge/log.md — append-only curator-side operation log\n"
        "\n"
        "## [{now}] bootstrap | workspace created\n"
    ),
```

Then change `create_seed_files` (currently lines ~198–206) from:

```python
def create_seed_files(workspace, today, domain):
    created = []
    for rel, template in SEED_FILES.items():
        p = workspace / rel
        if p.exists():
            continue  # don't clobber
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(template.format(today=today, domain=domain), encoding="utf-8")
        created.append(rel)
    return created
```

to:

```python
def create_seed_files(workspace, today, domain):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = []
    for rel, template in SEED_FILES.items():
        p = workspace / rel
        if p.exists():
            continue  # don't clobber
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            template.format(today=today, domain=domain, now=now), encoding="utf-8"
        )
        created.append(rel)
    return created
```

`datetime` is already imported (line 45). `str.format` ignores the extra `now=`
kwarg for templates that do not reference it, so the other seed files are
unaffected. Note `wiki/log.md` keeps its date-only `[{today}]` stamp — wiki log
entries are date-only by schema; only `.forge/log.md` uses full timestamps.

- [ ] **Step 4: Run the bootstrap tests to verify they pass**

Run: `python3 -m pytest tests/test_bootstrap.py -v`
Expected: PASS — the new test plus all pre-existing bootstrap tests.

- [ ] **Step 5: Write the failing submit.sh test**

Create `tests/test_request_human.py`:

```python
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
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python3 -m pytest tests/test_request_human.py -v`
Expected: FAIL — the logged timestamp ends in `T00:00:00Z`, not within 120s of now.

- [ ] **Step 7: Fix `submit.sh`**

In `.forge/skills/request-human/submit.sh`, change line 58 from:

```sh
today=$(date -u +%Y-%m-%d)
```

to:

```sh
today=$(date -u +%Y-%m-%d)
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Then change the log block (lines ~100–101) from:

```sh
[ -f "$log" ] && printf '\n## [%sT00:00:00Z] request-human | submitted %s (%s, %s)\n\n%s\n' \
    "$today" "$id" "$urgency" "$type" "$title" >> "$log"
```

to:

```sh
[ -f "$log" ] && printf '\n## [%s] request-human | submitted %s (%s, %s)\n\n%s\n' \
    "$now" "$id" "$urgency" "$type" "$title" >> "$log"
```

`today` is still used for the request `id` and the `created:` frontmatter field, so the line stays.

- [ ] **Step 8: Run the submit.sh test to verify it passes**

Run: `python3 -m pytest tests/test_request_human.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add .forge/lib/bootstrap.py .forge/skills/request-human/submit.sh tests/test_bootstrap.py tests/test_request_human.py
git commit -m "fix: log real UTC timestamps from bootstrap and request-human"
```

---

## Task 5: Fix 6 — remove the redundant queue channel

ingest pre-queues publicly-fetchable cited sources; explorer's citation-chain pass finds the same sources independently. Two channels → duplicate queue entries. Remove the ingest channel; make explorer the sole channel.

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md` (Step 9, "Surface follow-ups")
- Modify: `.forge/skills/explorer/SKILL.md` (signal "c) Citation chains")

- [ ] **Step 1: Edit `ingest/SKILL.md` Step 9**

In `.forge/skills/ingest/SKILL.md`, in the `### 9. Surface follow-ups` section, replace this bullet:

```markdown
If the source cites other sources you don't have:
- Publicly fetchable (arxiv, github, public docs) → add a note to `.forge/queue.md` for the explorer to pick up. Don't fetch inline.
- Paywalled or credentialed → write a request to `.forge/requests/inbox/<id>.md` (see request-human skill).
```

with:

```markdown
If the source cites other sources you don't have:
- Publicly fetchable (arxiv, github, public docs) → do **not** queue them here.
  The `explorer` skill's citation-chain pass walks `wiki/sources/` bodies and
  discovers cited-but-missing sources on its own; queueing them from ingest as
  well produces duplicate `.forge/queue.md` entries. Just make sure the citation
  is named in your `sources/<slug>.md` body so explorer can see it.
- Paywalled or credentialed → write a request to `.forge/requests/inbox/<id>.md` (see request-human skill).
```

- [ ] **Step 2: Edit `explorer/SKILL.md` citation-chain signal**

In `.forge/skills/explorer/SKILL.md`, in signal `**c) Citation chains.**`, append one sentence to the end of that paragraph so it reads:

```markdown
**c) Citation chains.** Walk every `wiki/sources/<slug>.md` and collect external references mentioned in the body (cited papers by name/DOI, linked repos, doc URLs). For each candidate target, count how many existing source pages mention it. This count is the **co-citation score**. This pass is the **sole** channel for cited-but-missing sources — ingest deliberately does not pre-queue them, so explorer will not see duplicate candidates.
```

- [ ] **Step 3: Review the diff**

Run: `git diff .forge/skills/ingest/SKILL.md .forge/skills/explorer/SKILL.md`
Expected: only the Step 9 bullet and the citation-chain paragraph changed.

- [ ] **Step 4: Commit**

```bash
git add .forge/skills/ingest/SKILL.md .forge/skills/explorer/SKILL.md
git commit -m "docs: explorer is the sole channel for cited-but-missing sources"
```

---

## Task 6: Fix 3 — document the MinerU ceiling in `explorer/SKILL.md`

explorer's fetch budget is size-based; it has no documented awareness of what ingest can actually process. Add a note so the budget and ingest capability share one mental model. (No budget-logic code change — Fix 2's token aligns the real ceilings.)

**Files:**
- Modify: `.forge/skills/explorer/SKILL.md` (the "Plan a bounded slate" budget section)

- [ ] **Step 1: Add the MinerU-ceiling note**

In `.forge/skills/explorer/SKILL.md`, in the `### 2. Plan a bounded slate` section, immediately after the `**Per-run budget (defaults):**` list (the three bullets ending with `≤ **200 MB** total download size ...`), insert this paragraph:

```markdown
**MinerU ceiling.** ingest normalizes PDFs and Office files through MinerU:
200 MB / 200 pages per file with a `MINERU_API_TOKEN` configured in
`.forge/secrets/credentials.env`, or 10 MB / 20 pages without one. A source
fetched beyond that ceiling will block in the queue (`[!]`) and produce a
request-human entry — so size the slate to what ingest can actually process,
not just to the 200 MB per-run budget above.
```

- [ ] **Step 2: Review the diff**

Run: `git diff .forge/skills/explorer/SKILL.md`
Expected: one paragraph added after the per-run budget list; nothing else.

- [ ] **Step 3: Commit**

```bash
git add .forge/skills/explorer/SKILL.md
git commit -m "docs: explorer notes the MinerU per-file ceiling"
```

---

## Task 7: Fix 4 — bootstrap Step 9 builds the index before the strict check

`bootstrap.md`'s contract invariant #8 promises `lint --strict` reports `0 error(s), 0 warning(s)`, but a seeded workspace emits a `stale-index` warning until the derived index is built. Run `lint --fix` first.

**Files:**
- Modify: `bootstrap.md` (Step 9)

- [ ] **Step 1: Edit `bootstrap.md` Step 9**

In `bootstrap.md`, replace the `### Step 9 — Verify the empty workspace` section's opening (the heading, the first `sh` code block, and the "Expected output" line) — currently:

```markdown
### Step 9 — Verify the empty workspace

```sh
python3 .forge/lib/lint.py --strict
```

Expected output: `0 error(s), 0 warning(s)` on the seeded pages (manifest, index, out_of_scope; `log.md` and other meta files do not count toward the page total).
```

with:

```markdown
### Step 9 — Verify the empty workspace

First build the derived index, then run the strict check:

```sh
python3 .forge/lib/lint.py --fix
python3 .forge/lib/lint.py --strict
```

`--fix` builds `wiki/index.md` and the `wiki/.meta/` index. Without it the
strict run reports a `stale-index` warning on the freshly seeded workspace.

Expected output of `--strict`: `0 error(s), 0 warning(s)` on the seeded pages (manifest, index, out_of_scope; `log.md` and other meta files do not count toward the page total).
```

- [ ] **Step 2: Review the diff**

Run: `git diff bootstrap.md`
Expected: only Step 9's command block and surrounding lines changed; the contract section and all other steps untouched.

- [ ] **Step 3: Commit**

```bash
git add bootstrap.md
git commit -m "fix: bootstrap Step 9 builds the index before the strict lint gate"
```

---

## Task 8: Fix 7 — gitignore the `.converted/` intermediate

`normalize.py` writes conversion output to `<stem>.converted/`. It is a regenerable intermediate and should not be committed.

**Files:**
- Modify: `templates/.gitignore.tmpl`
- Modify: `.gitignore`

- [ ] **Step 1: Edit `templates/.gitignore.tmpl`**

In `templates/.gitignore.tmpl`, after the last line (`.forge/lint-report.md`, line 42), append:

```
# raw-source conversion intermediates — regenerated by .forge/lib/normalize.py
*.converted/
```

- [ ] **Step 2: Edit the framework's own `.gitignore`**

In `.gitignore`, after the last line (`OBSIDIAN.md`), append:

```
# raw-source conversion intermediates — regenerated by .forge/lib/normalize.py
*.converted/
```

- [ ] **Step 3: Verify the pattern works**

Run: `git check-ignore -v $(mktemp -d)/x.converted/ 2>/dev/null; printf 'raw/papers/foo.converted/' | git check-ignore --stdin -v`
Expected: the `*.converted/` rule in `.gitignore` matches `raw/papers/foo.converted/`.

- [ ] **Step 4: Commit**

```bash
git add templates/.gitignore.tmpl .gitignore
git commit -m "fix: gitignore .converted/ raw-source conversion intermediates"
```

---

## Task 9: Integration verification

Confirm the framework fixes work end to end against a real bootstrapped workspace, including a real MinerU precision-API conversion. This task runs commands and inspects output; it does not commit code.

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full unit-test suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass (the 63 pre-existing plus the new credentials, wiki-search, bootstrap, and request-human tests).

- [ ] **Step 2: Create a fresh worktree off the fix branch**

```bash
git worktree add worktrees/wf-verify -b test/healthcheck-verify fix/healthcheck-2026-05-21
```

- [ ] **Step 3: Bootstrap it non-interactively**

Bootstrap `worktrees/wf-verify` by following `bootstrap.md`, reusing the
`multimodal-llm` interview answers from
`docs/superpowers/specs/2026-05-21-wikiforge-healthcheck-fixes-design.md`'s
sibling test (domain `multimodal-llm`). At Step 9, confirm the new two-command
sequence (`lint.py --fix` then `lint.py --strict`) reports
`0 error(s), 0 warning(s)` — verifying Fix 4.

- [ ] **Step 4: Install the MinerU token**

Edit `worktrees/wf-verify/.forge/secrets/credentials.env` and set the real
`MINERU_API_TOKEN` line (uncomment it and paste the token the user provided).
This file is gitignored — it is never committed.

- [ ] **Step 5: Verify cwd-independent credential loading (Fix 2)**

From inside the worktree, run Python with the working directory set to
`.forge/lib/` and confirm the token is found:

```bash
cd worktrees/wf-verify/.forge/lib && python3 -c "import credentials; print('MINERU_API_TOKEN' in credentials.load_credentials())"
```

Expected: `True` — proving `load_credentials()` resolves the credentials file regardless of cwd.

- [ ] **Step 6: Stage a large paper and ingest it via the precision API**

Copy `worktrees/multimodal-llm/raw/papers/2604.24763v2.pdf` (≈15 MB, >10 MB free-tier limit) into `worktrees/wf-verify/raw/papers/`, then run the ingest skill on it. Expected: MinerU routes through the **precision** API (`https://mineru.net/api/v4/file-urls/batch`), conversion succeeds, and a `wiki/sources/` page is drafted — no `[!]` blocked queue entry, no request-human entry for an oversize PDF. This verifies Fix 2 end to end.

- [ ] **Step 7: Verify search, lint, and clean tree**

Run, inside the worktree:
- `bin/wiki-search vision encoder fusion strategies` → returns ranked `[score N]` results (Fix 1).
- `python3 .forge/lib/lint.py --strict` → `0 error(s)` (regression check).
- `git status` → no `*.converted/` directory appears as untracked (Fix 7).

- [ ] **Step 8: Report findings and tear down**

Summarize: which fixes verified clean, any surprises. Then remove the verification worktree:

```bash
git worktree remove worktrees/wf-verify --force
git branch -D test/healthcheck-verify
```

---

## Self-Review

**Spec coverage:** Fix 1 → Tasks 2+3; Fix 2 → Task 1 (+ Task 9 end-to-end); Fix 3 → Task 6; Fix 4 → Task 7; Fix 5 → Task 4; Fix 6 → Task 5; Fix 7 → Task 8. All seven fixes plus the spec's verification section (Task 9) are covered.

**Placeholder scan:** No `TBD`/`TODO`/"handle edge cases"; every code step shows complete code; every doc step shows exact old and new text.

**Type/name consistency:** `DEFAULT_PATH`, `load_credentials`, `create_seed_files`, `SEED_FILES`, the `{now}` placeholder, `WIKI_ROOT`, the `[score N]` output format, and the `*.converted/` pattern are used consistently across tasks and tests.
