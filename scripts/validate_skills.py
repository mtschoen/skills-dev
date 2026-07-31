#!/usr/bin/env python3
"""Validate every skill's SKILL.md using the official Agent Skills validator.

Each top-level submodule in this repo is a skill with a SKILL.md at its root
(root layout). Per-skill validation is delegated to `agentskills validate`
(the console script from the pinned `skills-ref` PyPI package), which strict-
parses the YAML frontmatter and enforces the spec's naming/field rules.

This module keeps only the *fleet* logic the per-skill validator can't know:

  - the set of skills comes from `.gitmodules`, not from disk, so a broken
    recursive checkout can't pass vacuously;
  - empty/missing dir        -> ERROR (broken checkout);
  - content but no SKILL.md  -> SKIPPED (a WIP submodule, not a skill yet);
  - has a SKILL.md           -> handed to `agentskills validate`;
  - no tracked file (in the umbrella or any skill, dev files included)
    may reference local-only paths (user memory notes, machine-specific
    home directories) that do not travel with the repo.

Exit codes: 0 = all valid, 1 = validation errors, 2 = nothing validated.

Run from anywhere:  python scripts/validate_skills.py
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)

# Paths that exist only on the author's machines; tracked content may not
# reference them (internalize the content or drop the reference).
_PORTABILITY_RULES = (
    ("user memory note (~/.claude/notes/)", re.compile(r"\.claude[/\\]notes")),
    ("personal repo path", re.compile(r"~[/\\]schoen-claude-status")),
    (
        "machine-specific home path",
        re.compile(r"/home/schoen|C:[/\\]Users[/\\]mtsch|(?<![A-Za-z0-9])Y:\\"),
    ),
)

_PORTABILITY_EXEMPTIONS = {
    # running-spikes stores the spike notes it writes under ~/.claude/notes.
    "running-spikes": {"user memory note (~/.claude/notes/)"},
}

# These define and test the deny patterns, so they contain them literally.
_PORTABILITY_FILE_EXEMPTIONS = {
    "scripts/validate_skills.py",
    "tests/test_validate_skills.py",
}

# Fallback-walk skip list for directories git would not track anyway.
_SCAN_SKIP_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "workspace",
    "smoke-test-workspace",
}


def tracked_files(directory: Path):
    """Yield git-tracked files under *directory* (full walk if not a repo)."""
    listing = subprocess.run(
        ["git", "-C", str(directory), "ls-files", "-z"],
        capture_output=True,
        text=True,
    )
    if listing.returncode == 0:
        for name in listing.stdout.split("\0"):
            candidate = directory / name
            if name and candidate.is_file():
                yield candidate
        return
    for candidate in sorted(directory.rglob("*")):
        relative_parts = candidate.relative_to(directory).parts
        if candidate.is_file() and not _SCAN_SKIP_DIRECTORIES.intersection(
            relative_parts
        ):
            yield candidate


def check_portability(repo_root: Path, path: str):
    """Return error strings for local-only path references in tracked files."""
    exempt_labels = _PORTABILITY_EXEMPTIONS.get(path, set())
    errors = []
    for tracked in tracked_files(repo_root / path):
        relative = tracked.relative_to(repo_root).as_posix()
        if relative in _PORTABILITY_FILE_EXEMPTIONS:
            continue
        text = tracked.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in _PORTABILITY_RULES:
                if label not in exempt_labels and pattern.search(line):
                    errors.append(
                        f"{relative}:{line_number}: references a {label} "
                        "that does not travel with the repo"
                    )
    return errors


def parse_submodule_paths(gitmodules_text):
    """Return the ordered list of submodule paths declared in a .gitmodules file."""
    return _PATH_LINE.findall(gitmodules_text)


def find_skill_md(skill_dir: Path):
    """Return the root SKILL.md for a skill dir, or None if absent."""
    candidate = skill_dir / "SKILL.md"
    return candidate if candidate.is_file() else None


def has_content(skill_dir: Path):
    """True if the dir holds any file other than .git (i.e. it checked out)."""
    if not skill_dir.is_dir():
        return False
    return any(entry.name != ".git" for entry in skill_dir.iterdir())


def run_agentskills(skill_dir: Path):
    """Validate one skill dir with `agentskills validate`. Returns (exit_code, output).

    Raises RuntimeError if the `agentskills` console script isn't on PATH — a
    missing validator must fail loudly, never silently pass.
    """
    executable = shutil.which("agentskills")
    if executable is None:
        raise RuntimeError(
            "the 'agentskills' command was not found on PATH; "
            "install it with `pip install skills-ref==0.1.1`"
        )
    completed = subprocess.run(
        [executable, "validate", str(skill_dir)],
        capture_output=True,
        text=True,
    )
    return (completed.returncode, (completed.stdout + completed.stderr).strip())


import xml.etree.ElementTree as ET


def check_frontmatter_xml_wellformedness(skill_dir: Path, path: str):
    """Verify that SKILL.md frontmatter does not break XML parser when injected into prompt wrappers.

    Wraps the frontmatter in a simulated system-prompt XML container (`<skill><description>...</description></skill>`)
    and parses it using Python's builtin `xml.etree.ElementTree`. Any unescaped `<`, `>`, `&`, or invalid XML
    syntax will fail parsing and return a clear line-specific error.
    """
    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        return []
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    frontmatter = parts[1]

    # Wrap in a standard XML document structure to test well-formedness
    xml_doc = f"<skill>\n{frontmatter}\n</skill>"
    try:
        ET.fromstring(xml_doc)
        return []
    except ET.ParseError as err:
        line_no = err.position[0] if hasattr(err, "position") and err.position else 1
        return [
            f"{path}/SKILL.md:{line_no}: frontmatter breaks XML well-formedness: {err}"
        ]


def validate_skill(repo_root: Path, path: str, runner=run_agentskills):
    """Validate one skill. Returns a list of error strings ([] if clean or skipped).

    `runner(skill_dir) -> (exit_code, output)` is injected so the fleet logic is
    unit-testable without the real validator installed.
    """
    skill_dir = repo_root / path
    if find_skill_md(skill_dir) is None:
        if has_content(skill_dir):
            return []  # WIP submodule, not an authored skill yet — skip, not an error
        return [f"{path}: empty submodule dir, no SKILL.md — checkout looks broken"]

    errors = []
    code, output = runner(skill_dir)
    if code != 0:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines:
            errors.extend(f"{path}: {line}" for line in lines)
        else:
            errors.append(f"{path}: skills-ref reported invalid (exit {code})")
    errors.extend(check_frontmatter_xml_wellformedness(skill_dir, path))
    errors.extend(check_portability(repo_root, path))
    return errors


def validate_repo(repo_root: Path, runner=run_agentskills):
    """Validate every skill declared in .gitmodules.

    Returns (errors, validated_count, skipped) where validated_count is the
    number of submodules that had a SKILL.md, and skipped lists WIP submodules.
    """
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.is_file():
        return ([f"{repo_root}: no .gitmodules file found"], 0, [])

    paths = parse_submodule_paths(gitmodules.read_text(encoding="utf-8"))
    errors = list(check_portability(repo_root, "."))
    validated = 0
    skipped = []
    for path in paths:
        skill_errors = validate_skill(repo_root, path, runner=runner)
        if find_skill_md(repo_root / path) is not None:
            validated += 1
        elif not skill_errors:
            skipped.append(path)
        errors.extend(skill_errors)
    return (errors, validated, skipped)


def evaluate(repo_root: Path, runner=run_agentskills):
    """Run validation and return (exit_code, output_lines)."""
    errors, validated, skipped = validate_repo(repo_root, runner=runner)
    notices = [
        f"note: skipped {name} (submodule has no SKILL.md yet)" for name in skipped
    ]
    if errors:
        return (
            1,
            [
                f"skill validation failed ({len(errors)} issue(s)):",
                *(f"  - {error}" for error in errors),
                *notices,
            ],
        )
    if validated == 0:
        return (
            2,
            [
                "no skills with a SKILL.md were validated — refusing to pass "
                "vacuously (is the checkout broken?)",
                *notices,
            ],
        )
    return (0, [f"OK: all {validated} skills valid (agentskills)", *notices])


def main():
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
