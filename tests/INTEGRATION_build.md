# INTEGRATION — build: dangling-ref handling

Scope: verify that `build.py` (a) ships `confidence: placeholder` pages by
default, and (b) fails the build with a precise diagnostic if any prose or
typed-edge ref points at a dropped or missing slug. See
`docs/superpowers/specs/2026-05-25-build-dangling-refs-design.md` for the
design.

## Setup

Choose a scratch workspace. Example:

```sh
mkdir -p /tmp/wf-build-int && cd /tmp/wf-build-int
git init -q
# Copy a fresh bootstrapped wikiforge workspace here, or use one of the
# existing test worktrees under worktrees/wf-test-*.
```

For the rest of this runbook, `$WS` is the wikiforge workspace root.

## Scenario A — default build keeps placeholders

Pre-state:
- At least one page in `$WS/wiki/` has `confidence: placeholder`.
- At least one *other* page has a prose `[[<placeholder-slug>]]` reference.

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.0
```

Expected:
- Exit code 0.
- `dist/<name>-v0.1.0/` exists.
- The placeholder page is present in `dist/<name>-v0.1.0/wiki/<type>/<slug>.md`.
- `dist/<name>-v0.1.0/SKILL.md` contains the "## Known gaps" section.
- `dist/<name>-v0.1.0/wiki/.meta/pages.tsv` lists the placeholder page.

## Scenario B — `--drop-placeholders` fails on dangling refs

Pre-state: same as Scenario A.

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.1 --drop-placeholders 2> /tmp/wf-build-int.err
echo "exit=$?"
cat /tmp/wf-build-int.err
```

Expected:
- Exit code non-zero.
- stderr contains one `dangling-ref:` line per stale prose link plus one per
  stale typed edge, sorted by (from_slug, source, target).
- stderr ends with `build aborted: N dangling reference(s)` where N is the
  total count.
- `dist/<name>-v0.1.1/` does **not** exist (no partial bundle).

## Scenario C — `--drop-placeholders` succeeds after refs are removed

Pre-state: edit the page that referenced the placeholder. Remove the
`[[<placeholder-slug>]]` references (or replace with plain text).

Run:

```sh
cd $WS
python3 .forge/lib/build.py --workspace . --version 0.1.2 --drop-placeholders
```

Expected:
- Exit code 0.
- `dist/<name>-v0.1.2/` exists.
- The placeholder page is **absent** from `dist/<name>-v0.1.2/wiki/`.
- `dist/<name>-v0.1.2/wiki/.meta/pages.tsv` does not list the placeholder page.

## Cleanup

```sh
rm -rf $WS/dist/*-v0.1.0 $WS/dist/*-v0.1.1 $WS/dist/*-v0.1.2
```
