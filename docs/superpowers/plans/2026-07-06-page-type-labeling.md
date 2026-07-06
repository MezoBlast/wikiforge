# Page-Type Labeling Root-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operational, priority-ordered page-type decision procedure to the wikiforge scaffold so ingest stops defaulting everything to `concepts/`, and land it on `master` via PR.

**Architecture:** The fix is documentation/guidance only — no code. Two static (non-templated) scaffold files are edited: `schema.md` gains a "Choosing a page type" section and a rewritten type table; `.forge/skills/ingest/SKILL.md` Step 6 replaces its biased source→type table with the decision procedure, drops the "usually concepts" default, and adds a type-audit self-check. Work happens in an isolated git worktree off `master` so the large dirty `claude/bootstrapped` tree is untouched.

**Tech Stack:** Markdown, git worktrees, `gh` CLI, Python (existing `pytest` suite + `lint.py` as regression guards).

## Global Constraints

- No new page types; the six types are fixed.
- No `schema_version` bump — changes are additive guidance, not rule changes. Do NOT edit `.forge/lib/schema_spec.py`, `lint.py`, `index.py`, or `build.py`.
- Edit only these files: `schema.md`, `.forge/skills/ingest/SKILL.md` (+ the two design docs).
- No backfill of existing wiki pages in this plan.
- All edits land in a worktree off `master`; `claude/bootstrapped` and its dirty tree stay untouched.
- Branch name: `fix/page-type-labeling`. PR targets `master`.
- The spine wording is fixed: **entity = embodied (weights/data/repo or real person/org); convention = abstract practice; concept = residual abstract knowledge.**

---

### Task 1: Isolated worktree off master + design docs

**Files:**
- Create (worktree): a new working tree checked out at `master` on branch `fix/page-type-labeling`
- Create: `docs/superpowers/specs/2026-07-06-page-type-labeling-design.md` (copied into worktree)
- Create: `docs/superpowers/plans/2026-07-06-page-type-labeling.md` (this file, copied into worktree)

**Interfaces:**
- Produces: `$WT` = absolute path to the worktree root. **All later tasks operate with the worktree as the working directory**; file paths in Tasks 2–4 are relative to `$WT`.

- [ ] **Step 1: Create the worktree (via superpowers:using-git-worktrees)**

Invoke the `superpowers:using-git-worktrees` skill to create an isolated worktree at `master` on a new branch `fix/page-type-labeling`. Native fallback if needed:

```bash
git worktree add -b fix/page-type-labeling ../wikiforge-fix-page-type-labeling master
```

Set `WT` to the created path (e.g. `../wikiforge-fix-page-type-labeling`).

- [ ] **Step 2: Verify the worktree is clean and at master**

Run: `git -C "$WT" status -sb && git -C "$WT" log --oneline -1`
Expected: `## fix/page-type-labeling`, a clean tree (no modified/untracked files), and HEAD at master's tip commit `a335ecf docs(template): add granularity & dense-linking rule to CLAUDE.md.tmpl`.

- [ ] **Step 3: Confirm the two target files exist and are unmodified in the worktree**

Run: `git -C "$WT" ls-files schema.md .forge/skills/ingest/SKILL.md`
Expected: both paths printed (they are tracked static files on master).

- [ ] **Step 4: Copy the two design docs into the worktree**

The spec and this plan were authored in the main checkout; bring them into the worktree so they ship in the PR:

```bash
mkdir -p "$WT/docs/superpowers/specs" "$WT/docs/superpowers/plans"
cp docs/superpowers/specs/2026-07-06-page-type-labeling-design.md "$WT/docs/superpowers/specs/"
cp docs/superpowers/plans/2026-07-06-page-type-labeling.md "$WT/docs/superpowers/plans/"
```

- [ ] **Step 5: Commit the design docs**

```bash
git -C "$WT" add docs/superpowers/specs/2026-07-06-page-type-labeling-design.md docs/superpowers/plans/2026-07-06-page-type-labeling.md
git -C "$WT" commit -m "docs: spec + plan for page-type labeling root-fix"
```

Expected: one commit created on `fix/page-type-labeling`.

---

### Task 2: Add the decision procedure to `schema.md`

**Files:**
- Modify: `$WT/schema.md` (type table rows; new "Choosing a page type" section after the Page types block)

**Interfaces:**
- Consumes: nothing.
- Produces: a `## Choosing a page type` section that Task 3's ingest edit points to by name.

- [ ] **Step 1: Verify the biased/vague definitions are present (red check)**

Run: `grep -n "What something is — theory, methods, definitions" "$WT/schema.md" && grep -c "Choosing a page type" "$WT/schema.md"`
Expected: the concept row line prints; the count of "Choosing a page type" is `0`.

- [ ] **Step 2: Rewrite the type table rows (Read then Edit)**

Read `$WT/schema.md`, then Edit — replace this exact block:

```
| concept          | `wiki/concepts/`   | What something is — theory, methods, definitions.       |
| convention       | `wiki/conventions/`| How the field does things — notation, evaluation norms. |
| code-pattern     | `wiki/code-patterns/` | Canonical code with hard provenance.                 |
| claim            | `wiki/claims/`     | Testable assertions with evidence + counter-evidence.   |
| source           | `wiki/sources/`    | One summary per ingested raw source.                    |
| entity           | `wiki/entities/`   | People, labs, projects, tools.                          |
```

with:

```
| concept          | `wiki/concepts/`   | **Residual.** Abstract knowledge not covered by another type: general theory/definitions, or an entity's internal structure (taxonomy, results, pipeline, metric mechanism). |
| convention       | `wiki/conventions/`| An abstract normative practice — how the field conducts/reports evaluation (protocol, scoring scale, judging paradigm, aggregation rule). |
| code-pattern     | `wiki/code-patterns/` | Canonical code with hard provenance.                 |
| claim            | `wiki/claims/`     | Testable assertions with evidence + counter-evidence.   |
| source           | `wiki/sources/`    | One summary per ingested raw source.                    |
| entity           | `wiki/entities/`   | An embodied artifact (model, dataset, benchmark-project, tool — has weights/data/repo) or a real person/lab/organization. |
```

- [ ] **Step 3: Insert the "Choosing a page type" section**

Edit `$WT/schema.md` — replace this exact block (the divider + heading that follow the Page types section):

```
---

## Naming conventions
```

with:

```
---

## Choosing a page type

Pick a page's type with this **priority-ordered procedure — first match wins.**
The specific types are checked *before* `concept`; `concept` is the **residual**,
reached only when 1–5 do not apply. This ordering is deliberate — it stops
`concept` from becoming a catch-all.

1. **source** — the raw artifact you are ingesting (one per source, always).
2. **code-pattern** — canonical code you can pin to `repo` + `commit` + `path` +
   `lines`; a *located excerpt* of an implementation.
3. **claim** — a testable empirical assertion carrying evidence and/or
   counter-evidence ("X outperforms Y", "metric Z saturates").
4. **entity** — an **embodied** thing: a specific artifact with weights, data, or
   a repo (a model, dataset, benchmark-project, tool), or a real person / lab /
   organization. Singular, nominal identity.
5. **convention** — an **abstract normative practice**: *how the field conducts or
   reports evaluation* — a protocol, scoring scale, judging paradigm, or
   aggregation rule — owned by no single artifact and adopted across many.
6. **concept** (residual) — abstract knowledge that is none of the above: general
   theory, a definition or capability, or the **internal structure of an entity**
   (a benchmark's taxonomy, results table, pipeline, or a metric's mechanism).

### The spine: embodied vs. abstract

The hard boundary is **entity (embodied) vs. concept/convention (abstract)**:

- An **entity** is embodied — you obtain a *thing* (weights / data / repo) or it
  is a real person or organization. Among abstractions, a **convention** is a
  *practice* ("how the field evaluates") and a **concept** is *knowledge* ("what
  something is").
- **Citability and runnability are not criteria.** A judge model shipped inside
  another paper's release, with no standalone citation, is still an entity (it is
  embodied). A formula-metric is "runnable" but has no embodiment, so it is a
  concept.

### Tie-breakers

- **Paraphrase-identity test.** Rewrite *how it works* — is it still the same
  thing? Yes → **entity** (identity is its name; a named model survives a change
  to its internals). No → **concept/convention** (identity is its content; a named
  method stops being itself if you change what it means).
- **Entity vs. code-pattern.** Same artifact, different granularity: the whole
  named artifact is an **entity** (a reference node, no code body); a cited
  line-range of its source is a **code-pattern**.
- **Datasets.** The dataset-as-artifact is an **entity**; its schema/splits are a
  linked **concept**.
- **Metrics, split by embodiment.** A metric backed by weights or data (a trained
  reward/preference model) is an **entity**; a metric that is a formula or
  procedure (even if it invokes a separate model) is a **concept**, and the model
  it invokes is the entity.

The tell for entity-vs-convention is the verb: an entity **uses / reports /
applies** a convention. A benchmark-project (entity) *uses* a decomposition
paradigm (convention); a trained judge (entity) *applies* an aggregation rule
(convention). When X uses Y, X is the entity and Y the convention.

---

## Naming conventions
```

- [ ] **Step 4: Verify the section landed and types are all named (green check)**

Run:
```bash
grep -c "Choosing a page type" "$WT/schema.md"
for t in source code-pattern claim entity convention concept; do grep -q "\*\*$t\*\*" "$WT/schema.md" && echo "ok:$t" || echo "MISSING:$t"; done
grep -q "Residual" "$WT/schema.md" && echo "ok:residual"
```
Expected: count `1`; six `ok:<type>` lines; `ok:residual`.

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add schema.md
git -C "$WT" commit -m "docs(schema): add priority-ordered page-type decision procedure; concept is the residual"
```

---

### Task 3: Fix ingest Step 6 routing, default, and self-check

**Files:**
- Modify: `$WT/.forge/skills/ingest/SKILL.md` (Step 6 table → procedure; "usually concepts" default; completeness self-check)

**Interfaces:**
- Consumes: the `## Choosing a page type` section added to `schema.md` in Task 2 (referenced by name).
- Produces: nothing downstream.

- [ ] **Step 1: Verify the biased routing is present (red check)**

Run: `grep -n "usually \`concepts/\`" "$WT/.forge/skills/ingest/SKILL.md"; grep -n "Likely to draft / update" "$WT/.forge/skills/ingest/SKILL.md"`
Expected: both the "usually `concepts/`" default and the source→type table header print.

- [ ] **Step 2: Replace the source→type table with the decision procedure (Read then Edit)**

Read `$WT/.forge/skills/ingest/SKILL.md`, then Edit — replace this exact block:

```
Conditional drafts (only when warranted by the source):

| Source type | Likely to draft / update                                |
| ----------- | ------------------------------------------------------- |
| paper       | `concepts/`, `claims/`, `entities/`                     |
| repo        | `code-patterns/` (with provenance), maybe `entities/`   |
| doc         | `conventions/`                                          |
| web         | varies by content                                       |
| note        | varies; usually `concepts/` or `conventions/`           |
```

with:

```
**Choose each page's type with the decision procedure in `schema.md`
("Choosing a page type") — do not default to `concepts/`.** It is
priority-ordered, first match wins, and `concept` is the *residual* (reached only
when the specific types do not apply):

1. **source** — the raw artifact itself (always, one per source).
2. **code-pattern** — code pinned to `repo`+`commit`+`path`+`lines`.
3. **claim** — a testable assertion with evidence/counter-evidence.
4. **entity** — an *embodied* artifact (weights/data/repo: a model, dataset,
   benchmark-project, tool) or a real person/lab/org.
5. **convention** — an *abstract normative practice* (protocol, scoring scale,
   judging paradigm, aggregation rule) adopted across many artifacts.
6. **concept** (residual) — general theory/definitions, or the *internal structure
   of an entity* (a benchmark's taxonomy, results, pipeline, or a metric's
   mechanism).

A single source usually yields several pages of different types — a benchmark
paper yields a `source`, an `entity` hub for the benchmark, a `convention` for any
field-wide protocol it introduces, and `concepts` for its taxonomy/results. The
tell for entity-vs-convention: an entity **uses/reports/applies** a convention.
```

- [ ] **Step 3: Drop the "usually concepts" default in the exhaustive-extraction note (Edit)**

Edit `$WT/.forge/skills/ingest/SKILL.md` — replace this exact substring:

```
in a dedicated page (usually `concepts/`).
```

with:

```
in a dedicated page whose type you pick via the decision procedure above — a named embodied artifact → `entities/`, a field-wide evaluation practice → `conventions/`, an entity's internal structure or general theory → `concepts/`.
```

- [ ] **Step 4: Add a type-audit item to the Completeness self-check (Edit)**

Edit `$WT/.forge/skills/ingest/SKILL.md` — replace this exact block:

```
- **Counts reconciled?** Where the source states a total (e.g. "56 facets"), does
  your page enumerate that many?
```

with:

```
- **Counts reconciled?** Where the source states a total (e.g. "56 facets"), does
  your page enumerate that many?
- **Type audit?** Did you file a named embodied artifact (a model, dataset,
  benchmark-project, tool) or a field-wide evaluation practice as a `concept`?
  Re-check every new page against the decision procedure in `schema.md` — a named
  artifact belongs in `entities/`, a shared practice in `conventions/`; `concept`
  is only the residual.
```

- [ ] **Step 5: Verify the bias is gone and the procedure is present (green check)**

Run:
```bash
grep -q "usually \`concepts/\`" "$WT/.forge/skills/ingest/SKILL.md" && echo "STILL BIASED" || echo "ok:default-gone"
grep -q "Likely to draft / update" "$WT/.forge/skills/ingest/SKILL.md" && echo "TABLE STILL THERE" || echo "ok:table-gone"
grep -q "do not default to \`concepts/\`" "$WT/.forge/skills/ingest/SKILL.md" && echo "ok:procedure-present"
grep -q "Type audit?" "$WT/.forge/skills/ingest/SKILL.md" && echo "ok:type-audit"
```
Expected: `ok:default-gone`, `ok:table-gone`, `ok:procedure-present`, `ok:type-audit`.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add .forge/skills/ingest/SKILL.md
git -C "$WT" commit -m "docs(ingest): route page types via the decision procedure; drop concept default; add type-audit self-check"
```

---

### Task 4: Regression checks, push, open PR

**Files:**
- No edits. Runs existing tests/lint against the worktree, pushes, opens the PR.

**Interfaces:**
- Consumes: commits from Tasks 1–3 on `fix/page-type-labeling`.
- Produces: a PR into `master`.

- [ ] **Step 1: Bootstrap suite still passes (unchanged behavior)**

Run: `cd "$WT" && python3 -m pytest tests/test_bootstrap.py -q`
Expected: all tests pass. (We edited static files, not `templates/`, so bootstrap substitution is unaffected.)

- [ ] **Step 2: schema.md still matches the code mirror (no rule drift)**

Run:
```bash
cd "$WT" && python3 -c "import sys; sys.path.insert(0,'.forge/lib'); import schema_spec as S; print(sorted(S.PAGE_TYPES))"
for t in concept convention code-pattern claim source entity; do grep -q "\`wiki/${t}s/\`\|\`wiki/${t}-patterns/\`\|\`wiki/${t}/\`" schema.md || true; done
```
Expected: `['claim', 'code-pattern', 'concept', 'convention', 'entity', 'source']` — the six types are unchanged; we added no type and removed none.

- [ ] **Step 3: Lint smoke-test does not crash on the scaffold**

Run: `cd "$WT" && python3 .forge/lib/lint.py --report; echo "exit:$?"`
Expected: runs to completion (the pristine scaffold has a seed/empty wiki; the point is only that our doc edits introduce no crash). Note any pre-existing scaffold warnings as unrelated.

- [ ] **Step 4: Final grep sweep — the bias is gone repo-wide**

Run: `cd "$WT" && git grep -n "usually \`concepts/\`\|Likely to draft / update"`
Expected: no matches (exit status 1). If anything prints, a source→type default survived — fix before pushing.

- [ ] **Step 5: Push the branch**

Run: `git -C "$WT" push -u origin fix/page-type-labeling`
Expected: branch pushed to `origin`. (Shared-state action — authorized by the approved landing plan.)

- [ ] **Step 6: Open the PR into master**

```bash
gh pr create --repo MezoBlast/wikiforge --base master --head fix/page-type-labeling \
  --title "Fix page-type labeling at the root: add decision procedure" \
  --body "$(cat <<'EOF'
## Summary
- Root-fix the page-type imbalance (86 concepts / 0 conventions / 4 entities) by adding an operational, priority-ordered **decision procedure** to the scaffold, so ingest stops defaulting every structured extraction to `concepts/`.
- `schema.md`: new **"Choosing a page type"** section (procedure + embodied-vs-abstract spine + tie-breakers); `concept` redefined as the **residual**.
- `.forge/skills/ingest/SKILL.md` Step 6: biased source→type table replaced by the procedure; "usually concepts" default removed; **type-audit** added to the completeness self-check.
- Guidance-only: no new types, no `schema_version` bump, no code changes. Both files are static scaffold blobs, so the fix survives bootstrapping and propagates to every future bootstrapped wiki.

## Non-goals
- No backfill of existing mislabeled pages (separate follow-up).

## Test plan
- [ ] `pytest tests/test_bootstrap.py` passes (bootstrap behavior unchanged)
- [ ] `git grep "usually \`concepts/\`\|Likely to draft / update"` returns nothing
- [ ] `schema.md` "Choosing a page type" names all six types in priority order
- [ ] Spot-map known-mislabeled pages: gsb/mllm-as-a-judge → convention; mask2former/hps-v2-model → entity
EOF
)"
```

Expected: PR URL printed. Report it to the user.

- [ ] **Step 7: Report the PR URL**

Print the PR URL for the user to review and merge. Do not merge — the user reviews and merges.

---

## Self-Review

**1. Spec coverage:**
- Decision procedure (spec §The fix) → Task 2 Step 3, Task 3 Step 2. ✓
- Embodied-vs-abstract spine + tie-breakers (spec) → Task 2 Step 3. ✓
- schema.md type-table residual rewrite (spec §Changes 1) → Task 2 Step 2. ✓
- No `schema_version` bump (spec) → Global Constraints; Task 4 Step 2 verifies no type drift. ✓
- ingest table→procedure, drop default, type-audit (spec §Changes 2) → Task 3 Steps 2–4. ✓
- Bootstrapping-survival (spec) → static files edited in worktree off master; Task 4 Step 1 guards bootstrap tests. ✓
- Landing plan: worktree off master → PR (spec §Landing) → Task 1, Task 4 Steps 5–7. ✓
- Non-goal: no backfill → Global Constraints; PR body Non-goals. ✓

**2. Placeholder scan:** No TBD/TODO; every edit shows exact old/new content; every check has an exact command + expected output. ✓

**3. Type consistency:** Branch name `fix/page-type-labeling`, worktree var `$WT`, and the six type names are used identically across all tasks. The `schema.md` section title "Choosing a page type" referenced in Task 3 matches the heading created in Task 2. ✓
