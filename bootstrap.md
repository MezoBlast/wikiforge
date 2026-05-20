# bootstrap.md — wikiforge bootstrap runbook

You are an agent reading this file in a fresh clone of the wikiforge template repository. Your single job is to take this workspace from **template state** to **initialized state** by walking the steps below in order. After you complete them, this file is removed; `.forge/bootstrap.log` carries the completion record, and this runbook is never read again.

This runbook is imperative and **self-contained** — you do not need any other file to execute it. (Its design rationale lived in a `BOOTSTRAP_PLAN.md` spec during development; a fresh clone does not ship that spec and you do not need it.) Do not deviate from what's written here. Skipping a step or expanding the interview violates the contract.

## Prerequisites

- `git`, `git-lfs`, `python3` are installed and on `PATH`.
- `pip install -r requirements.txt` has been run (pulls in `pyyaml`).
- You are on a clean working tree (a fresh clone). You may be on `master` or on a branch you created for this run — Step 10 handles both.
- A human is available for a short synchronous interview (Step 2). This is the **only** synchronous human interaction in the entire wikiforge lifecycle.

Step 1 opens with a preflight probe that enforces the first two items. Do not skip it: a missing `git-lfs` otherwise surfaces only at Step 5, *after* the human has already answered all five interview questions.

## The contract (what success looks like)

When you finish, all of these must hold:

1. `bootstrap.md` is gone from the repo root.
2. `.forge/bootstrap.log` exists and contains one final-completion record.
3. No file that bootstrap *produces or substitutes* contains an unsubstituted `{{...}}` placeholder. That set is exactly: `purpose.md`, `wiki/{manifest,index,log,out_of_scope}.md`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `OBSIDIAN.md`, `.forge/notify.md`, `.gitignore`, `.gitattributes`. Out of scope for this check: `.forge/lib/*.py` (source files — `bootstrap.py` holds `{{...}}` strings as substitution keys) and `.forge/templates/*.tmpl` (bundle-build templates — they legitimately retain `@VAR@` placeholders for the *separate* build-time pass; note the distinct delimiter).
4. You are on a branch other than `master`/`main`; master remains pristine. The conventional name is `<agent>/bootstrapped` (e.g. `claude/bootstrapped`), but if you were already on a non-master branch when bootstrap began, committing there satisfies the contract.
5. There is at least one commit on that branch with message `bootstrap: <domain>`.
6. `git lfs ls-files` runs without error.
7. The four skills are discoverable under `.forge/skills/` and (best-effort) symlinked at `.claude/skills/wikiforge-*`.
8. `python3 .forge/lib/lint.py --strict` exits 0 with `0 error(s), 0 warning(s)` on the seeded workspace.

## Workflow

### Step 1 — Preflight, then detect partial bootstrap state

**Preflight.** Confirm the toolchain *before* touching anything or interviewing anyone:

```sh
for tool in git git-lfs python3; do
    command -v "$tool" >/dev/null 2>&1 || { echo "bootstrap: missing prerequisite: $tool" >&2; exit 1; }
done
python3 -c 'import yaml' >/dev/null 2>&1 || { echo "bootstrap: pyyaml missing — run: pip install -r requirements.txt" >&2; exit 1; }
```

If any check fails, **stop** and tell the human exactly what to install (`git-lfs`: `apt install git-lfs` / `brew install git-lfs`; `pyyaml`: `pip install -r requirements.txt`). Do not proceed into the interview — making someone answer five questions and then failing at Step 5 is the exact failure this probe exists to prevent.

**Detect partial state.** Then check for a prior bootstrap:

```sh
ls .forge/bootstrap.log 2>/dev/null
```

The log is markers-only. Step markers match `## [<timestamp>] step-N complete`; the final record matches `## [<timestamp>] BOOTSTRAP COMPLETE`. Scan for those anchored patterns:

- **Log absent or empty** → fresh bootstrap; continue to Step 2.
- **Log present with step markers but no final-completion record** → resumed bootstrap. Print the markers found, ask the human "resume from step N+1, or start over?", and proceed accordingly.
- **Log present with final-completion record** → already bootstrapped. Print the record, ask the human if they want to re-bootstrap. Do not auto-clobber. Stop unless they explicitly opt in (which requires they manually clear `.forge/bootstrap.log` first).

If the log file is corrupt or unreadable, **stop** and report. Do not guess.

### Step 2 — Interview the human

Five questions, **one at a time**. Capture answers in memory; print each one back for confirmation before asking the next. Do not batch.

| Q | Question | Validation |
| - | -------- | ---------- |
| Q1 | What's the **domain slug** for this wiki? Lowercase, hyphenated, no spaces. Examples: `neural-odes`, `cryo-em-imaging`. | Must match `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`. Reject whitespace, uppercase, special chars. |
| Q2 | In one paragraph (3–5 sentences), what does this wiki **cover**? Think "stable background knowledge an auto-research agent in this domain needs." | 50–800 characters. Reject shorter or longer. |
| Q3 | What are **3–5 specific questions** this wiki should be able to answer? Concrete beats abstract — "what's the canonical CIFAR-10 dataloader" beats "stuff about image classification." | 3–7 items. |
| Q4 | Name **3–5 specific things** this wiki will **not** cover, so consumer agents know to fall back to other tools. | ≥ 2 items. |
| Q5 | What kinds of **consumer agents** will use the produced bundles? One sentence per type. | ≥ 1 item. |

**Interview discipline:**

- Reject junk answers ("idk", "whatever", "...") with a brief explanation of why each answer matters; re-ask.
- Five questions is the budget. Do not invent additional questions. If the human volunteers more context, capture it in `raw/notes/bootstrap-extras.md` but do not let it expand the interview.
- If the human disengages or asks to defer: save partial answers to `.forge/bootstrap.log`, mark Step 2 incomplete, exit cleanly. Resumption via Step 1 picks up where they left off.
- If the human gives obviously bad answers despite re-prompting: flag the answers in the log, proceed anyway, and add `confidence: low` to the produced `purpose.md`.

After Q5, print all five answers together and ask: "Confirm to proceed?" Wait for yes.

Then write the marker:

```sh
echo "" >> .forge/bootstrap.log
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-2 complete (5 answers collected)" >> .forge/bootstrap.log
```

### Step 3 — Populate templates

Assemble the answers as a JSON object and pipe to the substitution helper:

```sh
cat <<'EOF' | python3 .forge/lib/bootstrap.py
{
    "domain": "<Q1 slug>",
    "scope": "<Q2 paragraph>",
    "key_questions": ["<Q3 item 1>", "<Q3 item 2>", "..."],
    "out_of_scope_items": ["<Q4 item 1>", "<Q4 item 2>", "..."],
    "anticipated_consumers": ["<Q5 item 1>", "<Q5 item 2>", "..."]
}
EOF
```

The helper:

- Walks every `*.tmpl` under `templates/`, substitutes placeholders (`{{domain}}`, `{{scope}}`, `{{key_questions}}`, `{{out_of_scope_items}}`, `{{anticipated_consumers}}`, `{{today}}`, `{{author}}`), writes the result to the corresponding path, drops `.tmpl`.
- Refuses to overwrite an existing target (exit 3 — means the workspace is dirty, abort).
- Scans every produced file for remaining `{{...}}` patterns and fails loudly (exit 4) if any are left (template bug; stop and report which file).
- Creates any missing directories (`raw/<types>`, `wiki/<types>`, `.forge/requests/<states>`, `.forge/secrets`, `dist`). Most already exist as `.gitkeep` stubs in the template, so typically only `dist/` is newly created.
- Creates seed append-only files (`wiki/index.md`, `wiki/log.md`, `.forge/queue.md`, `.forge/log.md`) with header lines.
- Best-effort creates `.claude/skills/wikiforge-{ingest,query,lint,explorer}` symlinks pointing at `.forge/skills/<name>/`. Returns `null` for `symlinks_created` if filesystem doesn't support symlinks; that's an optimization, not a contract.

Capture the helper's JSON output and log it:

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-3 complete" >> .forge/bootstrap.log
echo "# helper output:" >> .forge/bootstrap.log
echo '```json' >> .forge/bootstrap.log
# (append the JSON the helper printed)
echo '```' >> .forge/bootstrap.log
```

After Step 3, the `templates/` directory may be deleted:

```sh
rm -rf templates/
```

This is symmetric: bootstrap consumed the templates, they have served their purpose. Removing them keeps the bootstrapped workspace clean.

### Step 4 — Filesystem skeleton (verify)

Step 3 already created the directories and seed files. This step is a verification pass:

```sh
test -d raw/papers && test -d wiki/concepts && test -d .forge/requests/inbox || echo "MISSING DIR"
test -f wiki/index.md && test -f wiki/log.md && test -f .forge/queue.md && test -f .forge/log.md || echo "MISSING SEED"
```

If anything reports missing, the helper failed silently — stop and report.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-4 complete" >> .forge/bootstrap.log
```

### Step 5 — Initialize git LFS

The repository is already a git repo (you cloned it), and `git-lfs` was confirmed present by the Step 1 preflight. Initialize it and fail loudly if anything is wrong:

```sh
git lfs install --local || { echo "ERROR: git lfs install failed" >&2; exit 1; }
git lfs track 'raw/papers/**/*.pdf' 'raw/papers/**/*.PDF' >/dev/null 2>&1 || true
```

The `.gitattributes` already has the LFS patterns (written by Step 3). Verify both that LFS is functional and that the patterns are present — this is contract invariant 6:

```sh
git lfs ls-files >/dev/null 2>&1 || { echo "ERROR: git lfs not functional" >&2; exit 1; }
grep -q 'filter=lfs' .gitattributes || { echo "ERROR: .gitattributes missing LFS patterns" >&2; exit 1; }
```

Do **not** configure a git remote. That's the human's call after bootstrap.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-5 complete" >> .forge/bootstrap.log
```

### Step 6 — Wire up agent discovery (verify)

Step 3 attempted to create `.claude/skills/wikiforge-*` symlinks. Check whether it worked:

```sh
ls -la .claude/skills/ 2>/dev/null
```

- **If you see symlinks pointing at `../../.forge/skills/<name>`** — great, native autoload works.
- **If `.claude/skills/` exists but is empty** — symlink creation failed (Windows non-dev mode, restricted filesystem). This is NOT a bootstrap failure. The CLAUDE.md / AGENTS.md / GEMINI.md files Step 3 produced contain explicit pointers to each `.forge/skills/<name>/SKILL.md` — that's the contract; symlinks are the optimization.

Either way, verify that `.forge/skills/{ingest,query,lint,explorer,request-human}/SKILL.md` are all readable. If any is missing, stop and report — this is a template-repo bug.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-6 complete (symlinks: yes|no)" >> .forge/bootstrap.log
```

### Step 7 — Configure notifications (optional)

Ask the human: "Want to configure notifications for blocking human requests now? (y/n, default n)"

- **No / skip** → leave `.forge/notify.md` as-is (all channels commented out, default behavior is to log to `.forge/log.md`). Proceed.
- **Yes** → walk channel by channel:
  - **Slack webhook** — paste URL, validate it starts with `https://hooks.slack.com/services/`.
  - **ntfy.sh** — topic name, validate against `^[a-z0-9_-]+$`.
  - **email via sendmail** — recipient + SMTP config; offer to skip if it gets involved.

If the human pastes a malformed URL, re-prompt up to 3 times then store as-is with a `# WARN: failed validation` comment.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-7 complete (channels: <list-or-none>)" >> .forge/bootstrap.log
```

### Step 8 — Configure tool credentials (optional)

ingest and explorer call external tools to turn raw sources into markdown:
MinerU (PDF / Office → markdown) and the Tavily CLI (web URL → markdown). Both
have free tiers; API tokens unlock higher limits. Credentials live in
`.forge/secrets/credentials.env` — gitignored, local-only, never committed.
Step 3 seeded that file with a commented template.

Ask the human:

"Configure tool credentials now? (y/n, default n — you can edit
`.forge/secrets/credentials.env` by hand anytime later.)"

- **No / skip** → leave the seeded template as-is (all keys commented out;
  ingest falls back to free-tier tooling). Proceed.
- **Yes** → walk the human through each credential, one at a time. For each
  value the human provides, uncomment-and-fill the matching line in
  `.forge/secrets/credentials.env` (or append a new `KEY=value` line). Print
  the key *name* back for confirmation — never the value.

  1. **MinerU API token** — "Paste your MinerU API token (unlocks 200MB / 200
     pages per file), or press enter to skip (free tier: 10MB / 20 pages)."
     On a value, set `MINERU_API_TOKEN=<value>`.
  2. **Tavily API key** — "Paste your Tavily API key (`tvly-...`, used to fetch
     web sources), or press enter to skip." On a value, set
     `TAVILY_API_KEY=<value>`.
  3. **Additional credentials** — "Any other tool credentials to add now
     (audio transcription, OCR, ...)? Enter as `KEY=value`, or blank to
     finish." Loop, appending each line, until the human enters a blank line.

Credentials are optional and **not** a contract invariant — like notifications
(Step 7), this step exists so the human is not surprised later, and changes
nothing if skipped. The file is freely re-editable after bootstrap.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-8 complete (credentials: <key-names-or-none>)" >> .forge/bootstrap.log
```

### Step 9 — Verify the empty workspace

```sh
python3 .forge/lib/lint.py --strict
```

Expected output: `0 error(s), 0 warning(s)` on the seeded pages (manifest, index, out_of_scope; `log.md` and other meta files do not count toward the page total).

If lint fails: stop. Either the templates have a bug, the substitution produced invalid frontmatter, or the linter has a regression. Report which page failed which check. Do not proceed to Step 10 — a failed lint here means the workspace cannot be trusted as a clean foundation.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-9 complete (lint: 0/0)" >> .forge/bootstrap.log
```

### Step 10 — Branch, finalize, commit

This is where bootstrap diverges from master. Master stays pristine; the initialized state goes on a branch.

```sh
# Land the initialized state on a branch — never on master. If you are already
# on a non-master branch (a worktree, a CI branch, a branch you created for this
# run), commit there. Otherwise create the conventional <agent>/bootstrapped.
current=$(git branch --show-current)
case "$current" in
    master|main|"")
        AGENT_BRANCH="claude/bootstrapped"   # adapt to your runtime: gemini/, codex/, cursor/, ...
        git checkout -b "$AGENT_BRANCH"
        ;;
    *)
        AGENT_BRANCH="$current"
        echo "already on non-master branch '$current' — committing here"
        ;;
esac

# Remove the runbook. The log stays markers-only — do NOT cat the runbook into
# it, or Step 1's resumption scan on a future run will trip over the embedded
# '## [...]' headings. The runbook text remains recoverable from master's git
# history (`git show master:bootstrap.md`) if ever needed.
rm bootstrap.md

# Append the final-completion record to the markers-only log.
{
    echo ""
    echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] BOOTSTRAP COMPLETE | domain=<domain> | agent=<your-identifier>"
} >> .forge/bootstrap.log

# Stage and commit. `git add -A` does NOT pick up CLAUDE.md, AGENTS.md, GEMINI.md,
# OBSIDIAN.md, or .claude/skills/wikiforge-* — these are gitignored by design
# (see .gitignore). They are agent-runtime-specific local artifacts that live in
# the working tree and are regenerated by bootstrap on each fresh clone.
git add -A
git commit -m "bootstrap: <domain>"
```

What lands in this commit:

- `purpose.md`, `wiki/manifest.md`, `wiki/index.md`, `wiki/log.md`, `wiki/out_of_scope.md`
- `.forge/queue.md`, `.forge/log.md`, `.forge/notify.md`, `.forge/bootstrap.log`
- Any wiki pages, sources, raw clones, etc. that you may have already added (typically none at first bootstrap)

What stays local-only (regenerated by re-running bootstrap on a fresh clone of this branch):

- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `OBSIDIAN.md`
- `.claude/skills/wikiforge-*` symlinks (if the filesystem supports them)
- `.claude/memory/` (agent-side persistent context, never travels with the repo)

This split is intentional: substantive wiki content travels with the branch; agent-runtime-specific glue regenerates locally so different agent runtimes can coexist without clobbering each other.

If the rename or commit fails, stop. Do not commit a partial state. The human can manually recover.

### Step 11 — Brief the human

Print exactly this message (substituting `<domain>` and `<branch>`):

```
Bootstrap complete. Workspace initialized on branch <branch>; master is unchanged.

Next:
  1. Drop a few seed sources into raw/papers/ or raw/repos/, or paste arxiv/GitHub URLs
     and invoke the explorer skill (.forge/skills/explorer/SKILL.md).
  2. Then invoke the ingest skill (.forge/skills/ingest/SKILL.md) to process them
     into wiki pages.
  3. Open the folder in Obsidian when convenient; dashboards/ has curator views.

Git remote: not configured. To back this up, run:
    git remote add origin <url>
    git push -u origin <branch>

Tool credentials: edit .forge/secrets/credentials.env to add MinerU / Tavily
API keys (or any other tool tokens) — ingest works without them on free tiers.

Ongoing reference: README.md (overview), CLAUDE.md/AGENTS.md/GEMINI.md (skills),
schema.md (page-type spec).
```

Do not say more. The human just sat through a 10-minute interview; respect their time and stop.

## What bootstrap must NOT do

Restated so you don't drift:

- **No ingest.** Bootstrap stops at "workspace is ready." Processing raw sources is the ingest skill's job.
- **No schema modification.** `schema.md` is domain-agnostic and ships in finished form. Domain tweaks happen post-bootstrap if at all.
- **No git remote configuration.** Mentioned once in Step 10, otherwise ignored.
- **No sub-agent delegation.** You are the bootstrap agent; you do not spawn helpers.
- **No expansion of the question budget.** Five questions, not six.
- **No template authoring.** Bootstrap consumes `templates/`; if a template is missing, that's a repo bug — report and stop.
- **No touching master.** Step 9 ensures every bootstrap change is committed on a non-master branch — creating `<agent>/bootstrapped` if you began on master, or committing in place if you began on another branch. The commit never lands on `master`/`main`.

## Recovery

If bootstrap fails mid-run:

- The step-completion markers in `.forge/bootstrap.log` make resumption deterministic. Re-invoke bootstrap; Step 1 reads the markers and asks "resume or restart?"
- If the log itself is corrupted or the workspace state is unrecoverable, the cheapest fix is to delete the clone and start over from a fresh `git clone`. Bootstrap is short enough that re-running is always an option.
