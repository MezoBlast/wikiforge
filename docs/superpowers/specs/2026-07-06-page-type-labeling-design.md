# Design: root-fix the page-type labeling bias

- **Date:** 2026-07-06
- **Status:** approved (pending spec review)
- **Scope for today:** land the root guidance fix on `master` via PR; backfill of existing pages deferred to a later pass.

## Problem

The wiki's pages are badly skewed across the six types:

| Type | Count | Share |
|------|------:|------:|
| concept | 86 | 62% |
| source | 30 | 22% |
| claim | 15 | 11% |
| entity | 4 | 3% |
| convention | 0 | 0% |
| code-pattern | 0 | 0% |

`concepts/` is a catch-all; `conventions/` and `code-patterns/` are empty; `entities/` is barely used. Concrete symptoms verified by reading pages: field-wide evaluation *norms* are filed as concepts (`gsb-good-same-bad` self-describes as a "protocol"; `mllm-as-a-judge` as a "paradigm"), and embodied artifacts are filed as concepts (`mask2former` is a segmentation model; `hps-v2-model` a trained model), while benchmarks have no entity hub node at all.

## Root cause

Labeling is **entirely prose-guidance-driven**. `schema_spec.py` only *validates* field/edge correctness per type (`REQUIRED_FIELDS`, `ALLOWED_EDGE_TYPES`); it never *decides* a page's type. The type choice is made by the agent following `.forge/skills/ingest/SKILL.md`.

The bias has a single structural cause and a single location:

1. **`concept` is defined by inclusion, not as a residual.** `schema.md`'s type table defines concept as "what something is — theory, methods, definitions," which logically subsumes the other five (a taxonomy, a protocol, a model all "are" something). With overlapping, *descriptive* definitions and no *operational* test, "concept" is always a true answer and wins by default.
2. **The only concrete routing table steers papers away from conventions.** `.forge/skills/ingest/SKILL.md:181-187` maps `paper → concepts/, claims/, entities/` (no conventions) and `note → usually concepts`. Since 30/30 sources are papers, conventions never get created.
3. **The "usually `concepts/`" default** (`SKILL.md:194`) funnels all structured extraction into concepts.

Verified there is **no second seed**: `git grep` across all skills, `bootstrap.md`, and `templates/` shows the routing bias appears only in `ingest/SKILL.md`. `query/SKILL.md` merely lists types for `--type`; `templates/CLAUDE.md.tmpl:28` points readers to `schema.md` + the ingest skill (so fixing those two files flows through to every bootstrapped `CLAUDE.md`).

## The fix

Keep the six types (changing the set is schema-breaking and unnecessary). Add an **operational, priority-ordered decision procedure** and redefine `concept` as the **residual**.

### The spine: embodied vs. abstract

- **entity = embodied** — a specific artifact (weights / data / repo) or a real person / lab / org. Singular, nominal identity.
- **concept & convention = abstract** — no embodiment. **convention** is the abstract *practice* ("how the field evaluates"); **concept** is abstract *knowledge* ("what something is").
- **code-pattern** = a *located excerpt* of an entity's source code (repo+commit+path+lines).

Tie-breakers:
- **Paraphrase-identity test:** rewrite *how it works* — still the same thing? Yes → entity (identity is its name, e.g. Q-Judger survives changing its scoring internals). No → concept/convention (identity is its content, e.g. "bottom-up rubric scoring").
- **Entity vs. code-pattern:** the whole named artifact = entity (no code body); a cited line-range of its source = code-pattern.
- **Datasets:** the dataset-as-artifact → entity; its schema/splits → linked concept.
- **Metrics, split by embodiment:** weights/data-backed (ImageReward, HPS-v2) → entity; formula (FID, VQAScore, CLIPScore-the-computation) → concept.
- **Citability and runnability are NOT criteria:** Q-Judger has no standalone paper yet is an entity (embodied, shipped in the Qwen-Image-Bench release); a formula-metric is "runnable" but has no embodiment.

### The decision procedure (first match wins)

1. The raw artifact being ingested → **source** (always, one per source)
2. Canonical code with `repo`+`commit`+`path`+`lines` provenance → **code-pattern**
3. A testable empirical assertion with evidence/counter-evidence → **claim**
4. **Embodied** — a specific artifact (weights/data/repo) or a real person/lab/org → **entity**
5. An abstract **normative practice** — how the field conducts/reports evaluation (protocol, scoring scale, judging paradigm, aggregation rule) → **convention**
6. Otherwise — abstract knowledge: theory, definition, capability, or an entity's internal structure (taxonomy/results/pipeline/mechanism) → **concept** (residual)

The load-bearing change vs. today: **entity (4) and convention (5) are checked before concept (6)**, and concept is explicitly the residual.

## Changes (exactly two files + this spec)

### 1. `schema.md`
- Add a new section **"Choosing a page type"** (placed after the `## Page types` table): the decision procedure + the embodied-vs-abstract spine + the four tie-breakers above.
- Rewrite the `concept` row of the type table so its purpose reads as the **residual** ("general theory/definitions, or an entity's internal structure — reached only when the specific types do not apply"), and enrich the `entity`/`convention` rows with the embodied/abstract language.
- **No `schema_version` bump:** this is additive guidance, not a change to required fields, enums, or edge rules — `schema_spec.py`/`lint.py` stay correct as-is.

### 2. `.forge/skills/ingest/SKILL.md` (Step 6)
- Replace the source→type table (`SKILL.md:181-187`) with the decision procedure: a compressed inline copy plus a pointer to `schema.md`'s "Choosing a page type" section. Reframe the table as "types a source *may* yield," not a default routing.
- Delete the "usually `concepts/`" default phrasing (`SKILL.md:194`); replace with "route each structured extraction through the decision procedure — named artifacts → entities, shared practices → conventions, an entity's internal structure → concepts."
- Add a **type-audit** item to the Completeness self-check (`SKILL.md:286-298`): "Did you file a named embodied artifact, or a shared evaluation practice, as a `concept`? Re-check against the decision procedure."

## Non-goals (YAGNI)

- No new page types; no `schema_version` bump; no changes to `schema_spec.py` / `lint.py` / `index.py` / `build.py`.
- No backfill of the 86 existing pages today (separate follow-up pass, its own PR).
- No edits to `templates/` — `schema.md` and the skill are static, and the CLAUDE.md template already references them.

## Bootstrapping-survival analysis

The fix must survive the bootstrap process and ideally propagate to future wikis. Verified on `master`:
- `schema.md` and `.forge/skills/ingest/SKILL.md` are **static blobs** (repo root / `.forge/`), **not** under `templates/` and **not** `.tmpl` files.
- `bootstrap.py` step 1 substitutes *only* `templates/**/*.tmpl`; steps 2–5 seed append-only files, credentials, dirs, and symlinks — none rewrite `schema.md` or the skill.
- `bootstrap.md:23` states master remains pristine; bootstrapping runs on an `<agent>/bootstrapped` branch.

Therefore editing these two files (a) is never clobbered by a re-bootstrap, and (b) since master is the scaffold, benefits every future bootstrapped domain wiki.

## Landing plan (git)

- Create an **isolated worktree off `master`** (via `superpowers:using-git-worktrees`) so `claude/bootstrapped`'s large dirty working tree is untouched.
- Apply the two edits + commit this spec.
- Push the branch to `origin`; open a **PR into `master`** for review and merge.
- The 8 WIP commits on `claude/bootstrapped` stay off master.
- (Unrelated hygiene, noted not fixed: the `origin` URL embeds a plaintext GitHub PAT — worth rotating/moving to a credential helper later.)

## Verification

- `git grep` after edits confirms no remaining `paper → concepts` routing or "usually concepts" default.
- The new `schema.md` section names all six types in the priority order with a one-line trigger each.
- Sanity-map the known-mislabeled pages against the procedure (spot-check, not backfill): `gsb-good-same-bad`/`mllm-as-a-judge` → convention; `mask2former`/`hps-v2-model` → entity; `world-knowledge-grounding` → concept.
