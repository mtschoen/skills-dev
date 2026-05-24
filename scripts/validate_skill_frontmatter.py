#!/usr/bin/env python3
"""Validate the YAML frontmatter of every skill's SKILL.md.

Each top-level submodule in this repo is a skill whose SKILL.md opens with a
YAML frontmatter block (`name`, `description`). Claude Code parses that block
to index and trigger the skill; if it fails to parse, the skill silently loads
with no description (or not at all). This has bitten us more than once — e.g. a
`description: 'Use when you don't ...'` where the inner apostrophe terminates
the single-quoted scalar and breaks the parse.

The set of skills to check comes from `.gitmodules`, not from whatever happens
to be on disk. For each declared submodule:

  - empty/missing dir        -> ERROR (a recursive checkout that produced nothing
                                must fail loudly, never pass vacuously)
  - content but no SKILL.md  -> SKIPPED (a submodule that isn't an authored skill
                                yet, e.g. only a HANDOFF.md; install-skills.sh
                                skips these too)
  - has a SKILL.md           -> frontmatter parsed and validated

Exit codes: 0 = all valid, 1 = validation errors, 2 = nothing validated.

Run from anywhere — it locates the repo via this file:
    python scripts/validate_skill_frontmatter.py
"""
import re
import sys
from pathlib import Path

import yaml

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)


def parse_submodule_paths(gitmodules_text):
    """Return the ordered list of submodule paths declared in a .gitmodules file."""
    return _PATH_LINE.findall(gitmodules_text)


def find_skill_md(skill_dir: Path):
    """Locate the SKILL.md for a skill dir: root layout, or legacy skill-draft/."""
    for candidate in (skill_dir / "skill-draft" / "SKILL.md", skill_dir / "SKILL.md"):
        if candidate.is_file():
            return candidate
    return None


def has_content(skill_dir: Path):
    """True if the dir holds any tracked file other than .git (i.e. it checked out)."""
    if not skill_dir.is_dir():
        return False
    return any(entry.name != ".git" for entry in skill_dir.iterdir())


def extract_frontmatter(text: str):
    """Return the YAML block between the leading `---` fences, or None if absent.

    Tolerates CRLF (the Write tool emits LF on Windows, real files may be CRLF).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]) + "\n"
    return None


def validate_skill(repo_root: Path, path: str):
    """Validate one skill's SKILL.md frontmatter. Returns a list of error strings.

    Returns [] both for a clean skill and for a checked-out submodule that simply
    has no SKILL.md yet (a WIP). An empty/missing dir is an error.
    """
    skill_dir = repo_root / path
    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        if has_content(skill_dir):
            return []  # WIP submodule, not an authored skill yet — skip, not an error
        return [f"{path}: empty submodule dir, no SKILL.md — checkout looks broken"]

    where = skill_md.relative_to(repo_root).as_posix()
    text = skill_md.read_text(encoding="utf-8")

    frontmatter = extract_frontmatter(text)
    if frontmatter is None:
        return [f"{where}: missing or malformed '---' frontmatter delimiters"]

    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return [f"{where}: YAML parse error in frontmatter: {detail}"]

    if not isinstance(data, dict):
        return [f"{where}: frontmatter is not a key/value mapping"]

    errors = []
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{where}: 'name' is missing or empty")
    elif name.strip() != path:
        errors.append(f"{where}: 'name' is '{name.strip()}' but should match the skill dir '{path}'")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{where}: 'description' is missing or empty")

    return errors


def validate_repo(repo_root: Path):
    """Validate every skill declared in .gitmodules.

    Returns (errors, validated_count, skipped) where validated_count is the number
    of submodules that actually had a SKILL.md, and skipped lists WIP submodules.
    """
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.is_file():
        return ([f"{repo_root}: no .gitmodules file found"], 0, [])

    paths = parse_submodule_paths(gitmodules.read_text(encoding="utf-8"))
    errors = []
    validated = 0
    skipped = []
    for path in paths:
        skill_errors = validate_skill(repo_root, path)
        if find_skill_md(repo_root / path) is not None:
            validated += 1
        elif not skill_errors:
            skipped.append(path)
        errors.extend(skill_errors)
    return (errors, validated, skipped)


def evaluate(repo_root: Path):
    """Run validation and return (exit_code, output_lines)."""
    errors, validated, skipped = validate_repo(repo_root)
    notices = [f"note: skipped {name} (submodule has no SKILL.md yet)" for name in skipped]
    if errors:
        return (1, [f"frontmatter validation failed ({len(errors)} issue(s)):",
                    *(f"  - {error}" for error in errors), *notices])
    if validated == 0:
        return (2, ["no skills with a SKILL.md were validated — refusing to pass "
                    "vacuously (is the checkout broken?)", *notices])
    return (0, [f"OK: frontmatter valid for all {validated} skills", *notices])


def main():
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
