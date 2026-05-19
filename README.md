# wikiforge

A curator workspace template that produces portable, read-only knowledge bundles for AI auto-research agents. One repo per research domain. The wiki is the artifact; agents are the maintainers; bash is the consumer interface.

## States

The repo has two states.

- **Template state** (this `master` branch). Skeleton + skill specs + Python machinery + Obsidian config + bootstrap runbook. No domain decided yet. Files like `purpose.md`, `CLAUDE.md`, `wiki/manifest.md` do not exist — they are produced by bootstrap. Look in `templates/` and `bootstrap.md` if you want to inspect what bootstrap will generate.
- **Initialized state** (on a branch named like `claude/bootstrapped`). Bootstrap has run; the domain is named, templates substituted, agent-config files in place, linter passing on the seeded workspace. From here, the four skills (`ingest`, `query`, `lint`, `explorer`) operate the wiki.

Master stays pristine on purpose: you can pull fresh updates to schema, skills, lint rules, etc. into your bootstrapped branches without merge churn over substituted prose.

## To bootstrap

1. Clone the repo and ensure prerequisites are installed:

   ```sh
   git clone <your-clone-url> wikiforge-<your-domain>
   cd wikiforge-<your-domain>
   pip install -r requirements.txt        # only pyyaml
   git lfs install --local
   ```

2. Open `bootstrap.md` in your agent (or read it yourself if you're doing this by hand).
3. The agent walks the 10 steps in `bootstrap.md`. Step 2 is a five-question interview (domain slug, scope, key questions, out-of-scope items, anticipated consumers). The rest is mechanical.
4. Bootstrap commits the initialized state on a branch like `claude/bootstrapped`. Master is untouched.

The interview takes <10 minutes for an engaged human. Bootstrap as a whole runs once per workspace and is never re-read.

## Layout (template state)

```
.
├── README.md             # this file
├── schema.md             # page-type spec (domain-agnostic; ships as-is)
├── bootstrap.md          # one-shot runbook for the bootstrap agent
├── requirements.txt      # pyyaml
├── OBSIDIAN.md           # human-facing Obsidian setup notes (generic)
├── bin/                  # POSIX bash read scripts — used by curator AND ship in bundles
│   └── wiki-manifest  wiki-list  wiki-search  wiki-read  wiki-backlinks
├── templates/            # bootstrap input — .tmpl files; consumed (and deleted) at Step 3
│   ├── CLAUDE.md.tmpl  AGENTS.md.tmpl  GEMINI.md.tmpl
│   ├── purpose.md.tmpl
│   ├── wiki/manifest.md.tmpl  out_of_scope.md.tmpl
│   └── .forge/notify.md.tmpl
├── .forge/               # curator-only machinery (never travels into bundles)
│   ├── build.sh                 # bundle builder
│   ├── lib/                     # Python: schema_spec, frontmatter, wikilinks,
│   │                            # lint, build, provenance, ingest_helpers, bootstrap
│   ├── skills/                  # ingest, query, lint, explorer, request-human
│   │   └── <name>/SKILL.md
│   ├── skills/request-human/    # also has 4 .sh scripts: submit, check, archive, notify
│   └── templates/               # BUNDLE-build templates (not bootstrap templates):
│                                # SKILL.md.tmpl, MANIFEST.md.tmpl rendered by build.sh
├── .obsidian/            # vault config — graph colors, exclusion filters, plugin manifest
├── dashboards/           # Dataview views: orphans, stale, low-confidence, by-type, open-requests
├── raw/                  # .gitkeep stubs for papers/, repos/, docs/, web/, notes/
└── wiki/                 # .gitkeep stubs for concepts/, conventions/, code-patterns/,
                          # claims/, sources/, entities/
```

After bootstrap completes (on the bootstrapped branch), these additional files appear at the workspace root: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `purpose.md`, `wiki/manifest.md`, `wiki/index.md`, `wiki/log.md`, `wiki/out_of_scope.md`, `.forge/notify.md`, `.forge/queue.md`, `.forge/log.md`, `.forge/bootstrap.log`. The `templates/` directory is removed; `bootstrap.md` is renamed into `.forge/bootstrap.log`.

## Design references

- `.claude/README.md` — the project overview (why wikiforge exists, what it is and isn't, the two-artifact split).
- `.claude/plans/PLAN_Init.md` — the seven-phase implementation roadmap.
- `.claude/plans/BOOTSTRAP_PLAN.md` — the spec that `bootstrap.md` derives from.

## Repo conventions

- Master is template state and is pulled cleanly. Do not commit substituted files (no `CLAUDE.md`, `purpose.md`, etc.) to master.
- Bootstrapped state lives on branches: `claude/bootstrapped`, `gemini/bootstrapped`, etc. One branch per agent runtime, or per domain instance — your call.
- Agent memory (if your agent uses persistent memory files) lives under `.claude/memory/`, which is gitignored — it persists across branch switches in a single clone but does not travel with the repo.

## What this is not

A replacement for live retrieval. Wikiforge bundles cover the *stable, embarrassing-to-re-derive background* of a domain. Frontier results, fresh papers, fast-moving SOTA still come from web search and arxiv. The bundle is a layer of grounded vocabulary and convention beneath those live tools, not above them.

It is also not an experiment-running platform, an idea-generator, a paper-writer, or a research lifecycle manager. Other projects cover those phases. Wikiforge is the substrate underneath.
