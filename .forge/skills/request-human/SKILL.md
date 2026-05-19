---
name: wikiforge-request-human
description: Async file-based protocol for asking the human curator for resources the agent cannot fetch itself (paywalled papers, credentials, large downloads, money).
---

# request-human — async resource requests

The human is a **resource provider, not a reviewer**. You do not stop the wiki to ask permission for each page. You stop only when you can't get something yourself.

This skill is the file-based async protocol for those moments.

## When to use it

Use the request-human skill when you need:

- A paywalled paper (Nature, Science, paid IEEE/ACM, Elsevier, etc.)
- Credentials for a private repo, dataset, or API
- A large download that you don't want to consume bandwidth/time on without sign-off
- Anything that costs money
- A human judgement call where you've genuinely tried and can't proceed

Do NOT use it for:

- Things you can fetch yourself (use explorer instead)
- Per-page approval ("does this look right?") — that's reviewing, not provisioning
- Stalling. If you can act with the resources you have, do.

## Submit a request

```sh
.forge/skills/request-human/submit.sh \
    --agent ingest \
    --type paywalled-paper \
    --urgency blocking \
    --key "doi:10.1038/foo" \
    --title "Nature 2024 paper on X (DOI: 10.1038/foo)" <<'EOF'
## What I need
The Nature 2024 paper "Title here" (DOI: 10.1038/foo).

## Why
Three ingested sources cite this as canonical for the preprocessing step.
I can't write code-patterns/<slug>.md with confidence: > low without reading it.

## If granted
Drop the PDF into raw/papers/, then re-run ingest on the three citing sources.

## If denied
Mark code-patterns/<slug>.md with confidence: low and a stub note in the body
indicating the missing source. Add to wiki/out_of_scope.md if the topic should
be explicitly de-scoped.
EOF
```

The script writes `.forge/requests/inbox/<id>.md` where `<id>` is `YYYY-MM-DD-NNN` and returns the path on stdout.

**Required fields:**

- `--agent`: which skill is asking (ingest, explorer, query, lint, ...)
- `--type`: a stable type tag. Use one of: `paywalled-paper`, `credentialed-repo`, `large-download`, `paid-api`, `human-judgement`. Add new types only when none fit.
- `--urgency`: `blocking` (cannot proceed), `useful` (workaround exists), `nice-to-have` (improvement). Only `blocking` triggers notify.
- `--title`: short, scan-able by the human in their inbox.

**Optional:**

- `--key`: a deduplication key. If you set it (DOI, repo URL, dataset name), the script refuses to create a second open request with the same (type, key). Always set this for paper/repo/dataset requests so two agent sessions don't double-ask.

**Body sections** (in stdin) are mandatory by convention:

1. `## What I need` — the artifact, with enough specificity (DOI, URL, exact name)
2. `## Why` — the load-bearing reason, pointing to existing wiki pages where possible
3. `## If granted` — concrete actions you'll take when the resource arrives
4. `## If denied` — **the fallback plan, mandatory.** A denied request must not orphan work.

## Check for responses

```sh
.forge/skills/request-human/check.sh
```

Outputs one TSV line per pending response: `<id>\t<status>\t<title>`. Status is `granted`, `denied`, or `deferred`. Run this at the start of every session — there may be responses to prior requests that unblock queued work.

The session-start hook (Claude Code: `~/.claude/hooks/session_start.sh`; other agents: see runtime docs) should run `check.sh` automatically and surface the result into the agent's context.

## Archive resolved pairs

After acting on a response:

```sh
.forge/skills/request-human/archive.sh <id>
```

This moves both `inbox/<id>.md` and `responses/<id>.md` into `archive/<year>/<id>.md`, concatenated. Archive every resolved pair — leaving them around clutters `check.sh` output and reopens the dedup conflict surface.

## Response format (the human writes this)

```yaml
---
request_id: 2026-05-18-001
status: granted          # or denied | deferred
responded: 2026-05-18
artifacts:               # optional list of paths the human placed in-tree
  - raw/papers/nature-2024-foo.pdf
---

Optional human note. For deferred: when they expect to revisit. For denied: the reason.
```

## What this skill is **not**

- Not a chat channel. One request, one response. Iterate via new requests.
- Not a synchronous gate. If urgency is `useful` or `nice-to-have`, proceed with what you have and pick up the response when it arrives.
- Not a way to escalate disagreements. If you think the curator's `out_of_scope.md` is wrong, write a note in `.forge/log.md` — the human will see it in their next pass.
