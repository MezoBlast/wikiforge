# Ingest Granularity & Dense Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make wikiforge ingest extract structured content exhaustively and link densely, with self-describing placeholder-stub forward-links — encoded in the shipped guidance, one helper, and a report.

**Architecture:** Mostly guidance edits (`schema.md`, ingest/explorer SKILLs, `CLAUDE.md`, an integration runbook) plus two small Python changes: a `create_placeholder_stub()` helper in `ingest_helpers.py`, and a report-only "wanted pages" section in `lint.py`. No new page/edge types, no new lint error/warning codes, `bootstrap.py` unchanged. Behavior lives in files this instance ships; porting to the `.tmpl` master is deferred (checklist at end).

**Tech Stack:** Python 3 (stdlib + PyYAML via the local `frontmatter` module), pytest. Run Python through the repo venv: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3`. Tests auto-add `.forge/lib` to `sys.path` via `tests/conftest.py`.

---

## File structure

| File | Responsibility | Change |
| --- | --- | --- |
| `.forge/lib/ingest_helpers.py` | mechanical ingest utilities | **add** `create_placeholder_stub()` |
| `.forge/lib/lint.py` | linter + report writer | **add** `collect_stubs()`; extend `write_report()` + `main()` |
| `tests/test_ingest_helpers.py` | helper unit tests | **add** stub-helper tests |
| `tests/test_lint.py` | lint/report unit tests | **add** wanted-pages report tests |
| `schema.md` | page-spec / conventions | **edit** Body conventions; **add** forward-stub subsection |
| `.forge/skills/ingest/SKILL.md` | ingest workflow guidance | **edit** several sections |
| `.forge/skills/explorer/SKILL.md` | explorer workflow guidance | **edit** low-confidence signal |
| `CLAUDE.md` | curator entrypoint rules | **add** one hard rule |
| `tests/INTEGRATION_ingest.md` | manual ingest runbook | **add** one scenario |

Reference only (do not edit): `.forge/lib/frontmatter.py` (`dump(fm, body)`), `.forge/lib/schema_spec.py` (`DIR_TYPES`, `ENTITY_TYPE`), `.forge/lib/index.py` (`load_pages`).

---

## Task 1: `create_placeholder_stub()` helper

**Files:**
- Modify: `.forge/lib/ingest_helpers.py` (imports near line 11–15; new function appended after `slugify`, ~line 256)
- Test: `tests/test_ingest_helpers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingest_helpers.py`:

```python
def _make_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    for d in ("concepts", "conventions", "code-patterns", "claims", "sources", "entities"):
        (wiki / d).mkdir(parents=True)
    return wiki


def test_create_placeholder_stub_concept(tmp_path):
    _make_wiki(tmp_path)
    slug = ih.create_placeholder_stub(
        "concepts/clip-score", "CLIPScore",
        gloss="embedding-based text-image alignment metric.",
        linked_from="[[concepts/mllm-as-a-judge]] as a baseline",
        workspace_root=tmp_path,
    )
    assert slug == "concepts/clip-score"
    text = (tmp_path / "wiki/concepts/clip-score.md").read_text()
    assert "confidence: placeholder" in text
    assert "- stub" in text  # tags rendered as a yaml block list
    assert "**What it is:** embedding-based text-image alignment metric." in text
    assert "**Linked from:** [[concepts/mllm-as-a-judge]] as a baseline" in text
    assert "Expected scope" not in text  # omitted when arg absent
    assert "Source hint" not in text


def test_create_placeholder_stub_entity_ok(tmp_path):
    _make_wiki(tmp_path)
    ih.create_placeholder_stub(
        "entities/clip", "CLIP",
        gloss="vision-language model.",
        linked_from="[[concepts/clip-score]]",
        entity_type="tool",
        expected_scope="architecture and training.",
        source_hint="Radford et al. 2021",
        aliases=["Contrastive Language-Image Pretraining"],
        workspace_root=tmp_path,
    )
    text = (tmp_path / "wiki/entities/clip.md").read_text()
    assert "type: entity" in text
    assert "entity_type: tool" in text
    assert "**Expected scope:** architecture and training." in text
    assert "**Source hint:** Radford et al. 2021" in text
    assert "Contrastive Language-Image Pretraining" in text


def test_create_placeholder_stub_entity_requires_entity_type(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub(
            "entities/q-judger", "Q-Judger",
            gloss="a judge model.", linked_from="[[sources/x]]",
            workspace_root=tmp_path,
        )


def test_create_placeholder_stub_rejects_claim(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub(
            "claims/foo", "Foo", gloss="x.", linked_from="[[sources/y]]",
            workspace_root=tmp_path,
        )


def test_create_placeholder_stub_requires_gloss_and_linked_from(tmp_path):
    _make_wiki(tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub("concepts/a", "A", gloss="  ",
                                   linked_from="[[x]]", workspace_root=tmp_path)
    with pytest.raises(ValueError):
        ih.create_placeholder_stub("concepts/a", "A", gloss="ok.",
                                   linked_from="", workspace_root=tmp_path)


def test_create_placeholder_stub_idempotent(tmp_path):
    _make_wiki(tmp_path)
    kw = dict(gloss="x.", linked_from="[[concepts/a]]", workspace_root=tmp_path)
    first = ih.create_placeholder_stub("concepts/dup", "Dup", **kw)
    (tmp_path / "wiki/concepts/dup.md").write_text("SENTINEL", encoding="utf-8")
    second = ih.create_placeholder_stub("concepts/dup", "Dup", **kw)
    assert first == "concepts/dup"
    assert second is None
    assert (tmp_path / "wiki/concepts/dup.md").read_text() == "SENTINEL"


def test_create_placeholder_stub_lints_clean(tmp_path):
    import datetime
    import lint
    wiki = _make_wiki(tmp_path)
    (wiki / "concepts/a.md").write_text(
        "---\ntitle: A\ntype: concept\ncreated: '2026-01-01'\n"
        "last_verified: '2026-01-01'\nconfidence: likely\n---\n\nbody\n",
        encoding="utf-8")
    ih.create_placeholder_stub(
        "entities/clip", "CLIP", gloss="vlm.",
        linked_from="[[concepts/a]]", entity_type="tool",
        workspace_root=tmp_path)
    issues = lint.lint(wiki, tmp_path / "raw", 180, 30, datetime.date(2026, 6, 16))
    errors = [i for i in issues if i.severity == lint.ERROR]
    assert errors == []  # placeholder warnings are fine; zero errors
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/test_ingest_helpers.py -k placeholder_stub -v`
Expected: FAIL — `AttributeError: module 'ingest_helpers' has no attribute 'create_placeholder_stub'`.

- [ ] **Step 3: Add imports**

In `.forge/lib/ingest_helpers.py`, change the import block (currently lines 11–15):

```python
import hashlib
import re
from pathlib import Path
```

to:

```python
import datetime
import hashlib
import re
from pathlib import Path

import frontmatter
import schema_spec as S
```

(The existing `import frontmatter` line stays; add `import datetime` and `import schema_spec as S`. Do not duplicate `import frontmatter`.)

- [ ] **Step 4: Implement the helper**

Append to the end of `.forge/lib/ingest_helpers.py` (after `slugify`):

```python
STUBBABLE_TYPES = {"concept", "entity"}


def create_placeholder_stub(slug, title, *, gloss, linked_from,
                            expected_scope=None, source_hint=None,
                            entity_type=None, aliases=None, workspace_root="."):
    """Create wiki/<slug>.md as a self-describing confidence:placeholder stub.

    A forward-link target: lets ingest reference a concept/entity it has not
    written yet without tripping the broken-wikilink error. Idempotent — never
    overwrites an existing page. Returns the slug on creation, or None if the
    page already existed.

    Descriptive by construction: `gloss` (one sentence — what this node IS) and
    `linked_from` (verbatim context string, normally containing [[wikilinks]])
    are required, so the helper cannot emit a flat "TODO" stub. `expected_scope`,
    `source_hint`, and `aliases` are optional enrichment.

    Restricted to concepts/ and entities/ slugs. entities/ require entity_type.
    Raises ValueError for any other slug type, a missing/invalid entity_type, or
    an empty gloss / linked_from.
    """
    if not gloss or not str(gloss).strip():
        raise ValueError("gloss is required and must be non-empty")
    if not linked_from or not str(linked_from).strip():
        raise ValueError("linked_from is required and must be non-empty")
    top = slug.split("/", 1)[0] if "/" in slug else ""
    ptype = S.DIR_TYPES.get(top)
    if ptype not in STUBBABLE_TYPES:
        raise ValueError(
            f"refusing to stub {slug!r}: only concepts/ and entities/ pages are "
            f"stubbable (resolved type: {ptype!r})"
        )
    if ptype == "entity":
        if not entity_type:
            raise ValueError("entity stubs require entity_type")
        if entity_type not in S.ENTITY_TYPE:
            raise ValueError(
                f"invalid entity_type {entity_type!r}; "
                f"must be one of {sorted(S.ENTITY_TYPE)}"
            )
    page_path = Path(workspace_root) / "wiki" / f"{slug}.md"
    if page_path.exists():
        return None
    today = datetime.date.today().isoformat()
    fm = {
        "title": title,
        "type": ptype,
        "created": today,
        "last_verified": today,
        "confidence": "placeholder",
        "tags": ["stub"],
    }
    if aliases:
        fm["aliases"] = list(aliases)
    if ptype == "entity":
        fm["entity_type"] = entity_type
    lines = ["", "**Stub — needs filling.**", "",
             f"**What it is:** {str(gloss).strip()}"]
    if expected_scope:
        lines.append(f"**Expected scope:** {str(expected_scope).strip()}")
    lines.append(f"**Linked from:** {str(linked_from).strip()}")
    if source_hint:
        lines.append(f"**Source hint:** {str(source_hint).strip()}")
    body = "\n".join(lines) + "\n"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(frontmatter.dump(fm, body), encoding="utf-8")
    return slug
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/test_ingest_helpers.py -v`
Expected: PASS (all stub tests + the pre-existing tests).

- [ ] **Step 6: Commit**

```bash
git add .forge/lib/ingest_helpers.py tests/test_ingest_helpers.py
git commit -m "feat(ingest): add create_placeholder_stub for self-describing forward-links"
```

---

## Task 2: lint "wanted pages" report section

**Files:**
- Modify: `.forge/lib/lint.py` (add `collect_stubs`; extend `write_report` signature + body; update the one `write_report(...)` call in `main()`)
- Test: `tests/test_lint.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lint.py`:

```python
def test_collect_stubs_finds_placeholder_pages(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "concepts" / "clip-score.md").write_text(
        _page("title: CLIPScore\ntype: concept\ncreated: '2026-01-01'\n"
              "last_verified: '2026-01-01'\nconfidence: placeholder\ntags: [stub]"),
        encoding="utf-8")
    (wiki / "concepts" / "real.md").write_text(
        _page("title: Real\ntype: concept\ncreated: '2026-01-01'\n"
              "last_verified: '2026-01-01'\nconfidence: likely"),
        encoding="utf-8")
    stubs = lint.collect_stubs(wiki)
    assert ("concepts/clip-score", "CLIPScore") in stubs
    assert all(slug != "concepts/real" for slug, _ in stubs)


def test_report_lists_placeholder_stubs(tmp_path):
    report = tmp_path / "report.md"
    lint.write_report(report, [], [], [("concepts/clip-score", "CLIPScore")],
                      datetime.date(2026, 5, 20))
    text = report.read_text()
    assert "## Placeholder stubs / wanted pages" in text
    assert "[[concepts/clip-score]] — CLIPScore" in text


def test_report_no_stubs_renders_none(tmp_path):
    report = tmp_path / "report.md"
    lint.write_report(report, [], [], [], datetime.date(2026, 5, 20))
    text = report.read_text()
    assert "## Placeholder stubs / wanted pages" in text
    assert "_(none)_" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/test_lint.py -k "stub or wanted or placeholder" -v`
Expected: FAIL — `AttributeError: module 'lint' has no attribute 'collect_stubs'` and a `TypeError` on the 5-arg `write_report` call.

- [ ] **Step 3: Add `collect_stubs` and extend `write_report`**

In `.forge/lib/lint.py`, add this function immediately above `def write_report(` (currently line 390):

```python
def collect_stubs(wiki_dir):
    """Return sorted [(slug, title)] for confidence:placeholder pages — the
    'wanted pages' worklist (forward-link stubs awaiting fill)."""
    stubs = []
    for slug, _pt, fm, _body in index.load_pages(wiki_dir):
        if isinstance(fm, dict) and fm.get("confidence") == "placeholder":
            stubs.append((slug, fm.get("title", slug)))
    return sorted(stubs)
```

Change the `write_report` signature (line 390) from:

```python
def write_report(report_path, issues, gaps, today):
```

to:

```python
def write_report(report_path, issues, gaps, stubs, today):
```

Then, in `write_report`, find the gaps block that ends the function (currently lines 431–439):

```python
    out += ["", "## Open knowledge gaps", "",
            "`query-gap` entries from `.forge/feedback.md`, newest first.", ""]
    if gaps:
        for g in gaps:
            summary = g["lines"][0] if g["lines"] else ""
            out.append(f"- [{g['ts']}] severity: {g['severity']} — {summary}")
    else:
        out.append("_(none)_")
    report_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
```

and insert the stubs section just before the final `report_path.write_text(...)` line, so it becomes:

```python
    out += ["", "## Open knowledge gaps", "",
            "`query-gap` entries from `.forge/feedback.md`, newest first.", ""]
    if gaps:
        for g in gaps:
            summary = g["lines"][0] if g["lines"] else ""
            out.append(f"- [{g['ts']}] severity: {g['severity']} — {summary}")
    else:
        out.append("_(none)_")
    out += ["", "## Placeholder stubs / wanted pages", "",
            "`confidence: placeholder` pages — forward-link stubs and unfilled "
            "nodes. Excluded from the build; fill or supersede them.", ""]
    if stubs:
        for slug, title in stubs:
            out.append(f"- [[{slug}]] — {title}")
    else:
        out.append("_(none)_")
    report_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
```

- [ ] **Step 4: Pass `stubs` from `main()`**

In `.forge/lib/lint.py`, update the report block in `main()` (currently lines 481–484):

```python
    forge_dir = wiki_dir.parent / ".forge"
    if forge_dir.is_dir():
        gaps = collect_gaps(forge_dir / "feedback.md", args.gap_days, today)
        write_report(forge_dir / "lint-report.md", issues, gaps, today)
```

to:

```python
    forge_dir = wiki_dir.parent / ".forge"
    if forge_dir.is_dir():
        gaps = collect_gaps(forge_dir / "feedback.md", args.gap_days, today)
        stubs = collect_stubs(wiki_dir)
        write_report(forge_dir / "lint-report.md", issues, gaps, stubs, today)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/test_lint.py -v`
Expected: PASS (new tests + all pre-existing lint tests).

- [ ] **Step 6: Run the whole suite + a live lint to confirm no regression**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/ -q && PYTHONPATH=.forge/lib .forge/.venv/bin/python3 .forge/lib/lint.py --strict`
Expected: all tests pass; lint prints `0 error(s), …` and exits 0. Confirm `.forge/lint-report.md` now contains a `## Placeholder stubs / wanted pages` section.

- [ ] **Step 7: Commit**

```bash
git add .forge/lib/lint.py tests/test_lint.py
git commit -m "feat(lint): report placeholder stubs as a wanted-pages worklist"
```

---

## Task 3: `schema.md` — Body conventions + forward-stub subsection

**Files:**
- Modify: `schema.md` (Body conventions section, lines 272–279)

- [ ] **Step 1: Rewrite the Body conventions bullets**

In `schema.md`, replace the first bullet (line 274):

```markdown
- Markdown body (after the closing `---`) is freeform but should be brief: agents read pages whole. Aim for under ~300 lines per page; split into multiple linked pages if longer.
```

with:

```markdown
- **Narrative prose stays concise; structured content is captured in full.** A page's *prose* should be brief — agents read pages whole. But *structured, enumerable* content (taxonomies, workflows/pipelines, code structures with their key workflows and design ideas, metrics and tabular data, algorithm steps) must be captured **completely and faithfully**: reconcile counts/totals and cross-check a source's table against its appendix/figures. If a faithful reference page would run long (≫300 lines), **split it into linked pages** — never drop content to hit a length target.
```

Replace the wikilinks bullet (line 275):

```markdown
- Use `[[wikilinks]]` liberally in prose. Plain links are cheap; they enrich the backlink graph at zero cost.
```

with:

```markdown
- **Link densely — the graph is a product, not decoration.** Use `[[wikilinks]]` liberally in prose; every page should link out *and* be linked to. Create `concepts/`/`entities/` hub pages for recurring metrics, datasets, tools, and methods so multiple sources share nodes.
```

Replace the `sources/` bullet (line 279):

```markdown
- For `sources/` pages, the body is the agent's read of what the source contributes — key claims, gaps, suspect parts. One screen of text, not the full paper.
```

with:

```markdown
- For `sources/` pages, the body is the agent's read of what the source contributes — key claims, gaps, suspect parts. Keep it to one screen of *prose*; push exhaustive structured detail (taxonomies, tables, pipelines) into dedicated `concepts/` (or other typed) pages and link to them.
```

- [ ] **Step 2: Add the forward-stub subsection**

In `schema.md`, immediately after the Body conventions list (after the now-edited `sources/` bullet, before the next `---` or `## Index artifacts` heading at line 282), insert:

```markdown

### Forward-linking with placeholder stubs

A `[[wikilink]]` to a page that does not exist is a hard `broken-wikilink`
error, which would otherwise block forward references to concepts you have not
written yet. To link forward, create the target as a **placeholder stub**: a
`confidence: placeholder` page (tagged `stub`) carrying a one-line *What it is*
gloss and a *Linked from* context line. Stubs are excluded from the build,
surface as a worklist under `lint --report`'s `## Placeholder stubs / wanted
pages`, and are filled later by ingest/explorer. Create them with
`ingest_helpers.create_placeholder_stub()` — it is restricted to `concepts/` and
`entities/` and requires the gloss + linked-from context, so a stub is always
self-describing. Do **not** stub out-of-scope references (e.g. model-catalog
names); leave those as plain text.
```

- [ ] **Step 3: Verify and commit**

Run: `grep -n "Forward-linking with placeholder stubs" schema.md && grep -n "Link densely" schema.md`
Expected: both lines found.

```bash
git add schema.md
git commit -m "docs(schema): structured-content extraction and forward-link stubs"
```

---

## Task 4: `.forge/skills/ingest/SKILL.md` — extraction, linking, stubs, self-check

**Files:**
- Modify: `.forge/skills/ingest/SKILL.md` (step 6 at lines 189–194; "What ingest is not" at line 290; new section before line 275)

- [ ] **Step 1: Add the "Extract structured content exhaustively" block**

In `.forge/skills/ingest/SKILL.md`, immediately after the `code-patterns` paragraph (line 189) and before `**Cross-references:**` (line 191), insert:

```markdown
**Extract structured content exhaustively.** When a source contains *structured,
enumerable* material — a taxonomy, an evaluation rubric, a workflow or pipeline
(e.g. prompt-construction steps), a code module's key workflow and design ideas,
a metrics/results table, a dataset schema — capture it **completely and
faithfully** in a dedicated page (usually `concepts/`). Reconcile counts/totals
and cross-check a source's table against its appendix/figures. If the page would
run long, split it into linked pages — do not drop rows to hit a length target.
Keep the `sources/` page itself a brief prose note that links to these pages.

```

- [ ] **Step 2: Extend the Cross-references bullets**

In the same file, after the third Cross-references bullet (line 194, "Schema enforces which page types…"), append two bullets:

```markdown
- **Build the graph, don't just decorate it.** Every page should link out *and* be linked to. Create `concepts/`/`entities/` hub pages for recurring metrics, datasets, tools, and methods so multiple sources share nodes.
- **Forward-link with placeholder stubs.** To link a concept/entity you are not writing now, call `ingest_helpers.create_placeholder_stub(slug, title, gloss=..., linked_from=...)` so the `[[wikilink]]` resolves (a dangling link is a hard error). Stubs are `confidence: placeholder` (build-excluded) and become a "wanted pages" worklist. Stub only *in-scope* nodes; leave out-of-scope references (e.g. model names) as plain text.
```

- [ ] **Step 3: Reframe the "not a paper-summarizer" bullet**

In the same file, replace the bullet at line 290:

```markdown
- Not a paper-summarizer service. The source page is a curator note, not a comprehensive abstract.
```

with:

```markdown
- Not a *narrative*-summarizer service. The `sources/` page is a brief curator note, not a prose recap. But this brevity rule is about narrative only — **structured content (taxonomies, pipelines, code structures, metrics/tables, enumerations) is extracted in full** into dedicated pages (see "Extract structured content exhaustively" in step 6). Under-extracting a taxonomy is as much a failure as over-summarizing prose.
```

- [ ] **Step 4: Add the completeness self-check section**

In the same file, immediately before the `## Lint before you stop` heading (line 275), insert:

```markdown
## Completeness self-check

Before you finish, re-scan the source and your output:

- **Un-extracted structure?** Did the source contain a taxonomy, table, pipeline,
  or enumerable schema you *summarized* instead of capturing in full? Draft the
  dedicated page now.
- **Un-wired links?** Does every new page link out *and* have something linking
  to it? Wire missing edges; create placeholder stubs for in-scope targets you
  referenced but did not write.
- **Counts reconciled?** Where the source states a total (e.g. "56 facets"), does
  your page enumerate that many?

```

- [ ] **Step 5: Verify and commit**

Run: `grep -nF -e "Extract structured content exhaustively" -e "Forward-link with placeholder stubs" -e "Completeness self-check" -e "narrative*-summarizer service" .forge/skills/ingest/SKILL.md`
Expected: 4 matching lines (one per phrase). `-F` keeps the `*`/`#` literal and `-e` avoids BSD-grep's lack of `\|` alternation.

```bash
git add .forge/skills/ingest/SKILL.md
git commit -m "docs(ingest): exhaustive structured extraction, dense linking, stubs, self-check"
```

---

## Task 5: `.forge/skills/explorer/SKILL.md` — stubs as a fill worklist

**Files:**
- Modify: `.forge/skills/explorer/SKILL.md` (the `low-confidence` bullet, line 37)

- [ ] **Step 1: Extend the low-confidence signal bullet**

In `.forge/skills/explorer/SKILL.md`, replace the bullet at line 37:

```markdown
- `low-confidence` — pages whose `confidence:` is `low` or `placeholder`. Each needs a stronger or second source.
```

with:

```markdown
- `low-confidence` — pages whose `confidence:` is `low` or `placeholder`. Each needs a stronger or second source. **Placeholder pages tagged `stub`** are forward-link stubs ingest created as a "wanted pages" worklist (also listed under the report's `## Placeholder stubs / wanted pages`). Prioritize filling them: if a stub is fillable from sources already in `raw/`/`wiki/sources/`, note it as an ingest follow-up in your run log — you do **not** edit wiki pages or call ingest yourself; if it needs a new source, score it like any `low-confidence` fill.
```

- [ ] **Step 2: Verify and commit**

Run: `grep -n "Placeholder pages tagged" .forge/skills/explorer/SKILL.md`
Expected: the line is found.

```bash
git add .forge/skills/explorer/SKILL.md
git commit -m "docs(explorer): treat placeholder stubs as a fill worklist"
```

---

## Task 6: `CLAUDE.md` — granularity + linking rule

**Files:**
- Modify: `CLAUDE.md` (the "Hard rules" list — append a new numbered rule after rule 6)

- [ ] **Step 1: Add the rule**

In `CLAUDE.md`, find the "## Hard rules" section and append after its rule **6** ("Append-only state…"):

```markdown
7. **Granularity is high; the graph is the product.** Extract *structured* content (taxonomies, workflows, code structures, metrics/tables, enumerations) exhaustively into dedicated pages — keep only *narrative* prose brief. Cross-link densely: every page links out and is linked to. Forward-link via `ingest_helpers.create_placeholder_stub()`. See `schema.md` (Body conventions) and `.forge/skills/ingest/SKILL.md`.
```

- [ ] **Step 2: Verify and commit**

Run: `grep -n "Granularity is high; the graph is the product" CLAUDE.md`
Expected: the line is found.

```bash
git add CLAUDE.md
git commit -m "docs(claude): add high-granularity + dense-linking rule"
```

---

## Task 7: `tests/INTEGRATION_ingest.md` — new scenario

**Files:**
- Modify: `tests/INTEGRATION_ingest.md` (append a scenario at end of file, after line 117)

- [ ] **Step 1: Append the scenario**

Append to `tests/INTEGRATION_ingest.md`:

```markdown

## Scenario: structured extraction + placeholder stubs

**Setup:** ingest a paper containing a multi-level taxonomy or a large
criteria/metrics table (the Qwen-Image-Bench paper is a representative case).

**Expected:**

- A dedicated `concepts/<slug>-taxonomy` (or equivalent) page enumerates the
  structure **completely** — counts reconcile with any total the source states
  (e.g. a "56 facets" claim yields 56 enumerated facets). The `sources/` page
  stays a brief prose note that links to it.
- Forward references to not-yet-written concepts/entities resolve because ingest
  created `confidence: placeholder` stubs (tagged `stub`) via
  `ingest_helpers.create_placeholder_stub`. Each stub carries a one-line
  *What it is* gloss and a *Linked from* context line; none is a flat marker.
- `python3 .forge/lib/lint.py --strict` exits 0, and `--report` lists the new
  stubs under `## Placeholder stubs / wanted pages`.
- Out-of-scope references (e.g. evaluated model names) appear as plain text, not
  stubs.
```

- [ ] **Step 2: Commit**

```bash
git add tests/INTEGRATION_ingest.md
git commit -m "docs(test): ingest runbook scenario for structured extraction + stubs"
```

---

## Task 8: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 -m pytest tests/ -q`
Expected: all tests pass (no failures, no errors).

- [ ] **Step 2: Run a live strict lint over the real wiki**

Run: `PYTHONPATH=.forge/lib .forge/.venv/bin/python3 .forge/lib/lint.py --strict`
Expected: `0 error(s), …`; exit 0. (Existing placeholder/low-confidence warnings on the live wiki are acceptable.)

- [ ] **Step 3: Confirm the report section renders on the live wiki**

Run: `grep -n "## Placeholder stubs / wanted pages" .forge/lint-report.md`
Expected: the section header is present (its list may be `_(none)_` if no stubs exist yet).

---

## Port to master/template (deferred — out of plan scope)

When syncing the generator repo, port the same edits to the `.tmpl`/master copies of: `schema.md`, `.forge/skills/ingest/SKILL.md`, `.forge/skills/explorer/SKILL.md`, `.forge/lib/ingest_helpers.py`, `.forge/lib/lint.py`, `CLAUDE.md`, `tests/test_ingest_helpers.py`, `tests/test_lint.py`, `tests/INTEGRATION_ingest.md`. `bootstrap.py` needs no change.
```
