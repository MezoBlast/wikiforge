# bootstrap.md — wikiforge bootstrap runbook

You are an agent reading this file in a fresh clone of the wikiforge template repository. Your single job is to take this workspace from **template state** to **initialized state** by walking the steps below in order. After you complete them, this file is renamed into `.forge/bootstrap.log` and never read again.

This runbook is imperative. The reasoning behind each step lives in `.claude/plans/BOOTSTRAP_PLAN.md` — read it if you need to understand *why* something is done, but do not deviate from what's written here. Skipping a step or expanding the interview violates the contract.

## Prerequisites

- `git`, `git-lfs`, `python3` are installed and on `PATH`.
- `pip install -r requirements.txt` has been run (pulls in `pyyaml`).
- You are on the `master` branch with no uncommitted changes (a fresh clone).
- A human is available for a short synchronous interview (Step 2). This is the **only** synchronous human interaction in the entire wikiforge lifecycle.

## The contract (what success looks like)

When you finish, all of these must hold:

1. `bootstrap.md` is gone from the repo root.
2. `.forge/bootstrap.log` exists and contains one final-completion record.
3. No file contains an unsubstituted `{{...}}` placeholder.
4. You are on a branch named `<agent>/bootstrapped` (e.g. `claude/bootstrapped`) — not `master`. Master remains pristine.
5. There is at least one commit on that branch with message `bootstrap: <domain>`.
6. `git lfs ls-files` works.
7. The four skills are discoverable under `.forge/skills/` and (best-effort) symlinked at `.claude/skills/wikiforge-*`.
8. `python3 .forge/lib/lint.py --strict` exits 0 with `0 error(s), 0 warning(s)` on the seeded workspace.

## Workflow

### Step 1 — Detect partial bootstrap state

```sh
ls .forge/bootstrap.log 2>/dev/null
```

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
- Creates the empty directories (`raw/<types>`, `wiki/<types>`, `.forge/requests/<states>`, `.forge/secrets`, `dist`, plus `dashboards` if `.obsidian/` is present).
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

The repository is already a git repo (you cloned it). Just initialize LFS:

```sh
git lfs install --local
git lfs track 'raw/papers/**/*.pdf' 'raw/papers/**/*.PDF' 2>/dev/null || true
```

The `.gitattributes` already has the LFS patterns (written by Step 3). Verify:

```sh
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

### Step 8 — Verify the empty workspace

```sh
python3 .forge/lib/lint.py --strict
```

Expected output: `0 error(s), 0 warning(s)` on the seeded pages (manifest, index, out_of_scope; `log.md` and other meta files do not count toward the page total).

If lint fails: stop. Either the templates have a bug, the substitution produced invalid frontmatter, or the linter has a regression. Report which page failed which check. Do not proceed to Step 9 — a failed lint here means the workspace cannot be trusted as a clean foundation.

```sh
echo "## [$(date -u +%Y-%m-%dT%H:%M:%SZ)] step-8 complete (lint: 0/0)" >> .forge/bootstrap.log
```

### Step 9 — Branch, finalize, commit

This is where bootstrap diverges from the working tree on master. Master stays pristine; the initialized state goes on a branch.

```sh
# Pick a branch name based on your agent runtime. Examples:
#   claude/bootstrapped, gemini/bootstrapped, codex/bootstrapped, cursor/bootstrapped
AGENT_BRANCH="claude/bootstrapped"  # adapt to your runtime
git checkout -b "$AGENT_BRANCH"

# Rename bootstrap.md → .forge/bootstrap.log (append, do not overwrite — the log
# already has step markers from earlier steps).
cat bootstrap.md >> .forge/bootstrap.log
rm bootstrap.md

# Append the final-completion record.
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

### Step 10 — Brief the human

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
- **No touching master.** All file changes after Step 9's `git checkout -b` land on the bootstrapped branch.

## Recovery

If bootstrap fails mid-run:

- The step-completion markers in `.forge/bootstrap.log` make resumption deterministic. Re-invoke bootstrap; Step 1 reads the markers and asks "resume or restart?"
- If the log itself is corrupted or the workspace state is unrecoverable, the cheapest fix is to delete the clone and start over from a fresh `git clone`. Bootstrap is short enough that re-running is always an option.
