"""Rules, canonical configurations, and text invariants for check_config_drift."""

import re

# The shape every modal skill repo's .markdownlint-cli2.jsonc should have unless
# listed in MODAL_CONFIG_EXCEPTIONS below. MD013 (line length) and MD060 (table
# pipe style) are disabled everywhere by choice, uniformly.
CANONICAL_MODAL_CONFIG = {
    "config": {"default": True, "MD013": False, "MD060": False},
    "globs": ["**/*.md"],
    "ignores": ["node_modules"],
}

# Deviations from CANONICAL_MODAL_CONFIG, each proven necessary by a real
# `markdownlint-cli2` failure when the override was removed:
#   - MD041 (first-line-heading): escalate-over-shortcut, review-in-parallel,
#     docs-update, and project-maintenance keep it disabled.
#   - using-a-debugger's ignores list carries ".superpowers", a real local
#     scratch directory that exists in that repo (not gitignored elsewhere).
MODAL_CONFIG_EXCEPTIONS = {
    "escalate-over-shortcut": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "review-in-parallel-pipelines": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "docs-update": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "project-maintenance": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "using-a-debugger": {
        "config": {"default": True, "MD013": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules", ".superpowers"],
    },
}

# project-lock is not a modal skill repo: it predates the shared config shape.
PROJECT_LOCK_CONFIG = {
    "config": {"MD013": False, "MD041": False},
    "globs": ["**/*.md", "!workspace/**", "!.pi-subagents/**"],
    "ignores": ["node_modules", ".superpowers"],
}

FIXTURE_DIR_SEGMENTS = frozenset({"workspace", "mock_repo", "fixtures"})

FLEET_RUFF_PIN = "0.15.15"

# The literal UTF-8 bytes for U+2014 EM DASH.
_DEFAULT_ENCODING = "utf-8"
EM_DASH_BYTES = "\u2014".encode(encoding=_DEFAULT_ENCODING)

_SCAN_SKIP_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "workspace",
    "smoke-test-workspace",
}

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)
_EXTRA_SKILL_ROOT_GLOBS = ("packages/*/skills/*", "satellites/*/skills/*")

# Textual invariants for .github/workflows/lint.yml, checked without yaml
_MARKDOWNLINT_STEP = re.compile(r"markdownlint", re.IGNORECASE)
_PUSH_BRANCH_MAIN = re.compile(r"push:\s*\n\s*branches:\s*\[main\]")
_PULL_REQUEST_BRANCH_MAIN = re.compile(r"pull_request:\s*\n\s*branches:\s*\[main\]")
_WORKFLOW_DISPATCH = re.compile(r"^\s*workflow_dispatch\s*:", re.MULTILINE)
_TIMEOUT_MINUTES = re.compile(r"^\s*timeout-minutes\s*:", re.MULTILINE)

_RUFF_STEP = re.compile(r"\bruff\b")
_PYTEST_STEP = re.compile(r"\bpytest\b")
_SHELLCHECK_STEP = re.compile(r"shellcheck", re.IGNORECASE)

_RUFF_INSTALL_LINE = re.compile(r"(pip|pipx)\s+install\b.*\bruff\b|uvx\s+ruff@")
_RUFF_VERSION_REF = re.compile(r"ruff(?:==|@)([^\s'\"]+)")


def strip_jsonc_comments(text: str) -> str:
    """Remove `//` line comments from JSONC text, respecting string literals."""
    result = []
    in_string = False
    escape_next = False
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if in_string:
            result.append(character)
            if escape_next:
                escape_next = False
            elif character == "\\":
                escape_next = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue
        if character == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        result.append(character)
        index += 1
    return "".join(result)


def is_fixture_path(tracked_path: str) -> bool:
    """Return True if *tracked_path* sits under a known fixture directory."""
    directories = tracked_path.split("/")[:-1]
    return any(segment in FIXTURE_DIR_SEGMENTS for segment in directories)


def expected_markdownlint_config(path: str) -> dict:
    """Return the expected markdownlint configuration dict for a skill repo path."""
    if path == "project-lock":
        return PROJECT_LOCK_CONFIG
    return MODAL_CONFIG_EXCEPTIONS.get(path, CANONICAL_MODAL_CONFIG)


def ruff_pin_errors_in_text(label: str, text: str) -> list[str]:
    """Return pin-drift errors for ruff install lines in workflow text."""
    errors = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not _RUFF_INSTALL_LINE.search(line):
            continue
        match = _RUFF_VERSION_REF.search(line)
        if match is None:
            errors.append(
                f"{label}:{lineno}: installs ruff without a version pin "
                f"(expected =={FLEET_RUFF_PIN})"
            )
        elif match.group(1) != FLEET_RUFF_PIN:
            errors.append(
                f"{label}:{lineno}: pins ruff to {match.group(1)}, "
                f"fleet pin is {FLEET_RUFF_PIN}"
            )
    return errors
