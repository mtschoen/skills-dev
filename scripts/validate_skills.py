#!/usr/bin/env python3
"""Validate every skill's SKILL.md using the official Agent Skills validator.

Each shipped skill is declared in `.gitmodules` as a submodule path. A skill is:

  - the submodule directory if it contains `SKILL.md`, or
  - a one-level child directory under that submodule that contains `SKILL.md`.

This supports the family-submodule layout without adding unbounded recursion.

Per-skill validation is delegated to `agentskills validate`, the console script
from the pinned `skills-ref` PyPI package, which strict-parses the YAML
frontmatter and enforces the spec's naming and field rules.

This module keeps only the *fleet* logic the per-skill validator cannot know:

  - `.gitmodules` remains the source of truth for submodule-backed skills so a
    broken recursive checkout cannot pass vacuously;
  - empty/missing module dir -> ERROR (broken checkout);
  - submodule with content but no SKILL.md -> SKIPPED for WIP tracking;
  - has a SKILL.md -> handed to `agentskills validate`;
  - no tracked file (umbrella or skill dirs) may reference local-only paths that
    do not travel with the repo;
  - explicit extra roots can be scanned for relocated skills.
"""

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Collection
from pathlib import Path

import yaml

_DEFAULT_ENCODING = "utf-8"
_DEFAULT_ERRORS = "replace"
_BROKEN_CHECKOUT = "{}: empty submodule dir, no SKILL.md - checkout looks broken"
_BRACKET_ERR = (
    "{}: frontmatter description contains angle brackets, which Claude Code "
    "rejects in the prompt-injected description field"
)
_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
# The description scalar plus any indented continuation lines.
_DESCRIPTION = re.compile(
    r"^description\s*:\s*(?P<head>.*)(?P<rest>(?:\r?\n[ \t]+\S.*)*)",
    re.MULTILINE,
)

# Paths that exist only on the author's machines; tracked content may not
# reference them (internalize the content or drop the reference).
_PORTABILITY_RULES = (
    ("user memory note (~/.claude/notes/)", re.compile(r"\.claude[/\\]notes")),
    ("personal repo path", re.compile(r"~[/\\]schoen-claude-status")),
    (
        "machine-specific home path",
        re.compile(r"/home/schoen|C:[/\\]Users[/\\]mtsch|(?<![A-Za-z0-9])Y:\\"),
    ),
    ("personal infrastructure host", re.compile(r"llamabox|llamalab")),
)

_PORTABILITY_EXEMPTIONS = {}

_PORTABILITY_FILE_EXEMPTIONS = {
    "scripts/validate_skills.py",
    "tests/test_validate_skills.py",
}

_SCAN_SKIP_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "workspace",
    "smoke-test-workspace",
}

# Allowed frontmatter fields per the Agent Skills spec (skills-ref 0.1.1).
SPEC_FRONTMATTER_FIELDS = frozenset(
    {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
)

# Claude Code frontmatter extensions beyond the bare Agent Skills spec, taken
# from the "Frontmatter reference" table at
# https://code.claude.com/docs/en/skills.md (fetched 2026-10-15), minus the
# spec fields agentskills already accepts (name, description, allowed-tools,
# metadata, license, compatibility). skills-ref 0.1.1 rejects all of these.
CLAUDE_CODE_FRONTMATTER_FIELDS = frozenset(
    [
        "when_to_use",
        "argument-hint",
        "arguments",
        "disable-model-invocation",
        "user-invocable",
        "disallowed-tools",
        "model",
        "effort",
        "context",
        "agent",
        "background",
        "hooks",
        "paths",
        "shell",
    ]
)

_UNEXPECTED_FIELDS_LINE = re.compile(
    r"^(?P<prefix>-\s*)?Unexpected fields in frontmatter:\s*(?P<fields>.+?)\.\s+"
    r"(?P<suffix>Only \[.*\] are allowed\.)$"
)
_VALIDATION_HEADER = re.compile(r"^Validation failed for .*:$")

_EXTRA_SKILL_ROOT_GLOBS = ("packages/*/skills/*", "satellites/*/skills/*")


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
        if candidate.is_file() and not _SCAN_SKIP_DIRECTORIES.intersection(
            candidate.relative_to(directory).parts
        ):
            yield candidate


def check_portability(skill_root: Path, path: str):
    """Return error strings for local-only path references in tracked files."""
    skill_dir = skill_root
    report_prefix = path
    if path and not (skill_root / "SKILL.md").is_file():
        candidate = skill_root / path
        is_sub = candidate.is_dir() and (candidate / "SKILL.md").is_file()
        skill_dir, report_prefix = (candidate, path) if is_sub else (skill_dir, "")
    else:
        report_prefix = "" if path in ("", ".", "./") else path

    exempt_labels = _PORTABILITY_EXEMPTIONS.get(path, set())
    errors = []
    for tracked in tracked_files(skill_dir):
        relative = tracked.relative_to(skill_dir).as_posix()
        if relative in _PORTABILITY_FILE_EXEMPTIONS:
            continue
        text = tracked.read_text(encoding=_DEFAULT_ENCODING, errors=_DEFAULT_ERRORS)
        for _line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in _PORTABILITY_RULES:
                if label not in exempt_labels and pattern.search(line):
                    prefix = "" if report_prefix in ("", ".") else f"{report_prefix}/"
                    errors.append(
                        f"{prefix}{relative}:{_line_number}: references a {label} "
                        "that does not travel with the repo"
                    )
    return errors


def check_description_brackets(path: str, skill_md: Path):
    """Flag angle brackets in the frontmatter description (Claude Code rule)."""
    match = _FRONTMATTER.match(
        skill_md.read_text(encoding=_DEFAULT_ENCODING, errors=_DEFAULT_ERRORS)
    )
    if match is None:
        return []  # malformed frontmatter is skills-ref's finding, not ours
    described = _DESCRIPTION.search(match.group(1))
    if described is None:
        return []  # missing description is skills-ref's finding, not ours
    head = described.group("head").strip()
    if re.fullmatch(r"[>|][+-]?(?:\s+#.*)?", head):
        head = ""  # YAML block-scalar indicator (e.g. `>-`), not content
    if "<" in head or ">" in head or re.search(r"[<>]", described.group("rest")):
        return [_BRACKET_ERR.format(path)]
    return []


def parse_submodule_paths(gitmodules_text):
    """Return the ordered list of submodule paths declared in a .gitmodules file."""
    return _PATH_LINE.findall(gitmodules_text)


def discover_gitmodule_skills(repo_root: Path, module_paths):
    """Return skill paths and skip/error side lists from .gitmodules entries."""
    skill_paths, skipped, errors = [], [], []
    for path in module_paths:
        module_dir = repo_root / path
        if not module_dir.is_dir():
            errors.append(_BROKEN_CHECKOUT.format(path))
            continue
        if (module_dir / "SKILL.md").is_file():
            skill_paths.append(path)
            continue
        discovered = [
            f"{path}/{c.name}"
            for c in sorted(module_dir.iterdir())
            if c.is_dir() and not c.name.startswith(".")
        ]
        if discovered:
            skill_paths.extend(discovered)
        elif has_content(module_dir):
            skipped.append(path)
        else:
            errors.append(_BROKEN_CHECKOUT.format(path))
    return skill_paths, skipped, errors


def discover_extra_skill_directories(root: Path):
    """Yield `(label, directory)` for skill directories in extra roots."""
    for pattern in _EXTRA_SKILL_ROOT_GLOBS:
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_dir() and candidate.name != ".git":
                try:
                    label = candidate.relative_to(root).as_posix()
                except ValueError:
                    label = candidate.as_posix()
                yield label, candidate


def find_skill_md(skill_dir: Path):
    """Return the root SKILL.md for a skill dir, or None if absent."""
    candidate = skill_dir / "SKILL.md"
    return candidate if candidate.is_file() else None


def has_content(skill_dir: Path):
    """True if the dir holds any file other than .git (i.e. it checked out)."""
    return skill_dir.is_dir() and any(e.name != ".git" for e in skill_dir.iterdir())


def run_agentskills(skill_dir: Path):
    """Validate one skill dir with `agentskills validate`. Returns (exit_code, output)."""
    executable = shutil.which("agentskills")
    if executable is None:
        raise RuntimeError(
            "the 'agentskills' command was not found on PATH; "
            "install it with `pip install skills-ref==0.1.1`"
        )
    res = subprocess.run(
        [executable, "validate", str(skill_dir)], capture_output=True, text=True
    )
    return (res.returncode, (res.stdout + res.stderr).strip())


def extract_frontmatter_keys(skill_md: Path | None) -> set[str]:
    """Return top-level mapping keys in SKILL.md frontmatter, or an empty set."""
    if skill_md is None or not skill_md.is_file():
        return set()
    text = skill_md.read_text(encoding=_DEFAULT_ENCODING, errors=_DEFAULT_ERRORS)
    if not text.startswith("---"):
        return set()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return set()
    try:
        data = yaml.load(parts[1], Loader=yaml.BaseLoader)
    except Exception:
        return set()
    return {str(k) for k in data} if isinstance(data, dict) else set()


def filter_claude_code_fields(
    output: str, frontmatter_keys: Collection[str] | None = None
):
    """Return agentskills finding lines minus Claude Code's documented fields."""
    raw_keys = set(frontmatter_keys) if frontmatter_keys is not None else set()
    exempt_fields = raw_keys & CLAUDE_CODE_FRONTMATTER_FIELDS
    unknown_fields = sorted(
        raw_keys - SPEC_FRONTMATTER_FIELDS - CLAUDE_CODE_FRONTMATTER_FIELDS
    )

    kept = []
    for line in (raw.strip() for raw in output.splitlines()):
        if not line:
            continue
        match = _UNEXPECTED_FIELDS_LINE.match(line)
        if match is not None and exempt_fields:
            if not unknown_fields:
                continue
            prefix = match.group("prefix") or ""
            line = (
                f"{prefix}Unexpected fields in frontmatter: "
                f"{', '.join(unknown_fields)}. {match.group('suffix')}"
            )
        kept.append(line)
    return [] if all(_VALIDATION_HEADER.match(line) for line in kept) else kept


def check_frontmatter_xml_wellformedness(skill_dir: Path, path: str):
    """Verify that SKILL.md frontmatter is XML-compatible for prompt wrappers."""
    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        return []
    text = skill_md.read_text(encoding=_DEFAULT_ENCODING, errors=_DEFAULT_ERRORS)
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    xml_doc = f"<skill>\n{parts[1]}\n</skill>"
    try:
        ET.fromstring(xml_doc)
        return []
    except ET.ParseError as err:
        line_no = err.position[0] if hasattr(err, "position") and err.position else 1
        return [
            f"{path}/SKILL.md:{line_no}: frontmatter breaks XML well-formedness: {err}"
        ]


def validate_skill(skill_dir: Path, path: str, runner=run_agentskills):
    """Validate one skill. Returns a list of error strings ([] if clean or skipped)."""
    candidate = skill_dir / path
    if candidate.is_dir():
        skill_dir = candidate
        if path == "." or path == "":
            path = skill_dir.name
    if not skill_dir.is_dir():
        return [_BROKEN_CHECKOUT.format(path)]
    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        if has_content(skill_dir):
            return []  # WIP submodule path - skip, not an error
        return [_BROKEN_CHECKOUT.format(path)]

    errors = []
    frontmatter_keys = extract_frontmatter_keys(skill_md)
    code, output = runner(skill_dir)
    if code != 0:
        lines = filter_claude_code_fields(output, frontmatter_keys=frontmatter_keys)
        if lines:
            errors.extend(f"{path}: {line}" for line in lines)
        elif not output.strip():
            errors.append(f"{path}: skills-ref reported invalid (exit {code})")
    errors.extend(check_frontmatter_xml_wellformedness(skill_dir, path))
    errors.extend(check_description_brackets(path, skill_md))
    errors.extend(check_portability(skill_dir, path))
    return errors


def validate_repo(repo_root: Path, runner=run_agentskills):
    """Validate every skill declared in `.gitmodules`."""
    return validate_repo_with_options(repo_root=repo_root, runner=runner)


def validate_repo_with_options(
    repo_root: Path, runner=run_agentskills, extra_skill_roots=None
):
    """Validate `.gitmodules` skills and optionally explicit extra-scan root skills."""
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.is_file():
        return ([f"{repo_root}: no .gitmodules file found"], 0, [])

    module_paths = parse_submodule_paths(
        gitmodules.read_text(encoding=_DEFAULT_ENCODING)
    )
    skills, skipped, errors = discover_gitmodule_skills(repo_root, module_paths)
    errors.extend(check_portability(repo_root, "."))

    validated = 0
    for path in skills:
        skill_dir = repo_root / path
        skill_errors = validate_skill(skill_dir, path, runner=runner)
        if find_skill_md(skill_dir) is not None:
            validated += 1
        else:
            skipped.append(path)
        errors.extend(skill_errors)

    seen = {str((repo_root / path).resolve()) for path in skills}
    for extra_root in extra_skill_roots or []:
        root_path = Path(extra_root)
        for label, candidate in discover_extra_skill_directories(root_path):
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            skill_errors = validate_skill(candidate, label, runner=runner)
            errors.extend(skill_errors)
            if not skill_errors:
                validated += 1
    return (errors, validated, skipped)


def evaluate(repo_root: Path, runner=run_agentskills, extra_skill_roots=None):
    """Run validation and return (exit_code, output_lines)."""
    errors, validated, skipped = validate_repo_with_options(
        repo_root, runner=runner, extra_skill_roots=extra_skill_roots
    )
    notices = [f"note: skipped {n} (submodule has no SKILL.md yet)" for n in skipped]
    if errors:
        return (
            1,
            [
                f"skill validation failed ({len(errors)} issue(s)):",
                *(f" - {error}" for error in errors),
                *notices,
            ],
        )
    if validated == 0:
        return (
            2,
            [
                "no skills with a SKILL.md were validated - refusing to pass "
                "vacuously (is the checkout broken?)",
                *notices,
            ],
        )
    return (0, [f"OK: all {validated} skills valid (agentskills)", *notices])


def main():
    parser = argparse.ArgumentParser(
        description="Validate skill metadata and tracked file portability."
    )
    parser.add_argument(
        "--extra-skill-root",
        action="append",
        default=[],
        help="scan an additional repo root for relocated skills",
    )
    args, _ = parser.parse_known_args()
    code, lines = evaluate(
        Path(__file__).resolve().parent.parent,
        runner=run_agentskills,
        extra_skill_roots=args.extra_skill_root,
    )
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
