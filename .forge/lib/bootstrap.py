#!/usr/bin/env python3
"""bootstrap.py — substitution + seed helper for the bootstrap workflow.

The bootstrapping agent reads `bootstrap.md` for the imperative steps. After
collecting Q1-Q5 answers it pipes a JSON object to this script, which:

  1. Walks every `.tmpl` file under `templates/`, substitutes the placeholders,
     writes to the corresponding target path, and removes the `.tmpl` suffix.
  2. Creates the seed empty append-only files (`wiki/index.md`, `wiki/log.md`,
     `.forge/queue.md`, `.forge/log.md`) with header lines.
  3. Creates the empty directories required by the workspace layout
     (raw/, wiki/<types>/, .forge/requests/, .forge/secrets/).
  4. Optionally creates `.claude/skills/wikiforge-*` symlinks pointing at the
     skill directories under `.forge/skills/`.

Input format (JSON on stdin):

  {
    "domain": "neural-odes",
    "scope": "...one paragraph...",
    "key_questions": ["q1", "q2", "q3"],
    "out_of_scope_items": ["item1", "item2", "item3"],
    "anticipated_consumers": ["agent type 1", "agent type 2"],
    "author": "Optional name; defaults to git config user.name",
    "today": "Optional YYYY-MM-DD; defaults to UTC today"
  }

Output (stdout, JSON):

  {
    "substituted": [list of (template, target) pairs],
    "seed_files_created": [list of paths],
    "directories_created": [list of paths],
    "symlinks_created": [list of (link, target) pairs] or null on failure
  }

Exit codes:
  0 — success
  2 — invalid input (missing required field, bad type)
  3 — file conflict (target already exists; refuses to overwrite)
  4 — unfilled placeholder detected after substitution (template bug)
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED = ("domain", "scope", "key_questions", "out_of_scope_items", "anticipated_consumers")
SLUG_RE = __import__("re").compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
UNFILLED_RE = __import__("re").compile(r"\{\{[a-zA-Z_]+\}\}")


def err(msg, code=2):
    print(f"bootstrap.py: {msg}", file=sys.stderr)
    sys.exit(code)


def get_git_user():
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "user.name"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return out or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def fmt_bullets(items):
    """Format a list of strings as markdown bullets, one per line."""
    if isinstance(items, str):
        items = [items]
    return "\n".join(f"- {s}" for s in items)


def validate(answers):
    for k in REQUIRED:
        if k not in answers:
            err(f"missing required field: {k!r}")
    if not SLUG_RE.match(answers["domain"]):
        err(f"domain must be lowercase [a-z0-9-]; got {answers['domain']!r}")
    if not (50 <= len(answers["scope"]) <= 800):
        err(f"scope must be 50-800 chars; got {len(answers['scope'])}")
    if not (3 <= len(answers["key_questions"]) <= 7):
        err(f"key_questions: 3-7 items; got {len(answers['key_questions'])}")
    if len(answers["out_of_scope_items"]) < 2:
        err(f"out_of_scope_items: at least 2; got {len(answers['out_of_scope_items'])}")
    if len(answers["anticipated_consumers"]) < 1:
        err("anticipated_consumers: at least 1 item")


def build_subs(answers):
    return {
        "{{domain}}": answers["domain"],
        "{{scope}}": answers["scope"].strip(),
        "{{key_questions}}": fmt_bullets(answers["key_questions"]),
        "{{out_of_scope_items}}": fmt_bullets(answers["out_of_scope_items"]),
        "{{anticipated_consumers}}": fmt_bullets(answers["anticipated_consumers"]),
        "{{today}}": answers.get("today") or datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        "{{author}}": answers.get("author") or get_git_user(),
    }


def substitute(workspace, subs):
    templates_root = workspace / "templates"
    if not templates_root.is_dir():
        err(f"no templates dir at {templates_root}", code=2)

    substituted = []
    for tmpl in sorted(templates_root.rglob("*.tmpl")):
        rel = tmpl.relative_to(templates_root).with_suffix("")  # drop .tmpl
        target = workspace / rel
        text = tmpl.read_text(encoding="utf-8")
        for k, v in subs.items():
            text = text.replace(k, v)
        remaining = UNFILLED_RE.findall(text)
        if remaining:
            err(f"unfilled placeholders in {target}: {sorted(set(remaining))}", code=4)
        if target.exists():
            # ok if existing content matches what we'd write — handles the case
            # where the master repo ships a static .gitignore that the template
            # also produces (no placeholders to substitute)
            existing = target.read_text(encoding="utf-8")
            if existing == text:
                substituted.append([str(rel) + ".tmpl", str(rel) + " (unchanged)"])
                continue
            err(f"refuse to overwrite existing with different content: {target}", code=3)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        substituted.append([str(rel) + ".tmpl", str(rel)])
    return substituted


def create_directories(workspace):
    dirs = [
        "raw/papers", "raw/repos", "raw/docs", "raw/web", "raw/notes",
        "wiki/concepts", "wiki/conventions", "wiki/code-patterns",
        "wiki/claims", "wiki/sources", "wiki/entities",
        ".forge/requests/inbox", ".forge/requests/responses",
        ".forge/requests/archive", ".forge/secrets",
        "dist",
    ]
    if (workspace / ".obsidian").exists():
        dirs.append("dashboards")
    created = []
    for d in dirs:
        p = workspace / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(d)
    return created


SEED_FILES = {
    "wiki/index.md": (
        "---\n"
        "title: index\n"
        "type: index\n"
        "created: \"{today}\"\n"
        "last_verified: \"{today}\"\n"
        "---\n"
        "\n"
        "# Index\n"
        "\n"
        "Catalog of all pages in this wiki, grouped by type. Agents append entries here when ingesting; the linter can also rebuild this file via `python3 .forge/lib/lint.py --fix`.\n"
        "\n"
        "## concepts\n\n## conventions\n\n## code-patterns\n\n## claims\n\n## sources\n\n## entities\n"
    ),
    "wiki/log.md": (
        "# wiki/log.md — append-only wiki operation record\n"
        "<!-- See schema.md for entry format. Most-recent at the bottom. -->\n"
        "\n"
        "## [{today}] bootstrap | wikiforge-{domain}\n"
        "\n"
        "Workspace bootstrapped.\n"
    ),
    ".forge/queue.md": (
        "# .forge/queue.md — append-only ingest queue\n"
        "<!-- See schema.md or .forge/skills/ingest/SKILL.md for entry format. -->\n"
        "<!-- States: [ ] pending  [~] in progress  [x] done  [!] blocked. -->\n"
    ),
    ".forge/log.md": (
        "# .forge/log.md — append-only curator-side operation log\n"
        "\n"
        "## [{today}T00:00:00Z] bootstrap | workspace created\n"
    ),
}


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


SKILL_LINKS = {
    "wikiforge-ingest": "../../.forge/skills/ingest",
    "wikiforge-query": "../../.forge/skills/query",
    "wikiforge-lint": "../../.forge/skills/lint",
    "wikiforge-explorer": "../../.forge/skills/explorer",
}


def create_symlinks(workspace):
    """Best-effort: create .claude/skills/wikiforge-* symlinks. Return list or None."""
    sk_dir = workspace / ".claude" / "skills"
    try:
        sk_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    created = []
    for name, target in SKILL_LINKS.items():
        link = sk_dir / name
        if link.exists() or link.is_symlink():
            continue
        try:
            os.symlink(target, link)
            created.append([str(link.relative_to(workspace)), target])
        except OSError:
            return None  # symlinks not supported; signal partial-failure
    return created


def main():
    try:
        answers = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        err(f"invalid JSON on stdin: {e}")
    validate(answers)
    subs = build_subs(answers)
    workspace = Path(os.environ.get("WORKSPACE", ".")).resolve()
    if not (workspace / "templates").is_dir():
        err(f"no templates/ dir at {workspace}; cwd is {Path.cwd()}; pass WORKSPACE env var or run from workspace root")

    substituted = substitute(workspace, subs)
    directories_created = create_directories(workspace)
    seed_files_created = create_seed_files(workspace, subs["{{today}}"], subs["{{domain}}"])
    symlinks_created = create_symlinks(workspace)

    result = {
        "domain": subs["{{domain}}"],
        "today": subs["{{today}}"],
        "substituted": substituted,
        "directories_created": directories_created,
        "seed_files_created": seed_files_created,
        "symlinks_created": symlinks_created,
    }
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
