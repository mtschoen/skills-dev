"""Rules, canonical configurations, and text invariants for check_config_drift."""

import fnmatch
import re

import yaml

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


# Ruff subcommands, skipped when reading a `ruff <subcommand> <paths>` run
# line so the subcommand word itself is not mistaken for a path argument.
RUFF_SUBCOMMAND_TOKENS = frozenset({"check", "format"})


def parse_workflow_yaml(text: str) -> dict:
    """Parse a GitHub/Gitea Actions workflow file into a plain dict.

    Returns an empty dict for an empty or non-mapping document so callers can
    treat "no jobs" and "unparseable" uniformly as "nothing configured" rather
    than crashing on a workflow file that is present but nearly empty.
    """
    document = yaml.safe_load(text)
    return document if isinstance(document, dict) else {}


def _normalize_directory(value) -> str:
    """Normalize a working-directory value to a plain, slash-free-edges path.

    "", ".", and "./" all mean "the checkout root" and normalize to "".
    """
    text = str(value or "").strip()
    if text in ("", ".", "./"):
        return ""
    if text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def join_relative_directory(working_directory: str, value: str) -> str:
    """Join a step's working-directory with a path/scandir value it names."""
    directory = _normalize_directory(value)
    working_directory = _normalize_directory(working_directory)
    if not directory:
        return working_directory
    if not working_directory:
        return directory
    return f"{working_directory}/{directory}"


def iter_workflow_steps(workflow: dict):
    """Yield (working_directory, step) for every step in a parsed workflow.

    working_directory is normalized (see _normalize_directory) and resolved
    from the step's own `working-directory`, falling back to its job's
    `defaults.run.working-directory`, falling back to the workflow-level
    default. A workflow with no `jobs:` mapping but a bare top-level
    `steps:` list (used by this guard's own test fixtures) is treated as one
    implicit job, so callers do not need real GitHub Actions job scaffolding
    to exercise this against a step list directly.
    """
    if not isinstance(workflow, dict):
        return
    workflow_working_directory = _normalize_directory(
        ((workflow.get("defaults") or {}).get("run") or {}).get("working-directory")
    )
    jobs = workflow.get("jobs")
    if isinstance(jobs, dict):
        job_specs = list(jobs.values())
    elif isinstance(workflow.get("steps"), list):
        job_specs = [workflow]
    else:
        job_specs = []
    for job in job_specs:
        if not isinstance(job, dict):
            continue
        job_working_directory = _normalize_directory(
            ((job.get("defaults") or {}).get("run") or {}).get(
                "working-directory", workflow_working_directory
            )
        )
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            working_directory = _normalize_directory(
                step.get("working-directory", job_working_directory)
            )
            yield working_directory, step


def _classify_token(token: str) -> tuple[str, str]:
    """Classify a command-line path argument as a directory or a file/glob.

    A bare `.` means "the whole working directory" (a directory target). A
    token holding a glob character, or whose final path segment has a `.`
    (an extension - `deploy.sh`, `scripts/*.sh`), is a specific file/glob
    (matched by exact/glob comparison). Anything else (`evals`, `tests/`,
    `scripts/`) is a directory a tool would recurse into (matched by prefix).
    """
    if token in (".", "./"):
        return "dir", token
    if any(character in token for character in "*?["):
        return "glob", token
    if "." in token.rsplit("/", 1)[-1]:
        return "glob", token
    return "dir", token


# Shell command-separator tokens ("&&", "||", ";", "|"), used to split a run
# line into individual command invocations before matching a tool name, so a
# tool name is only read as an invocation when it leads its own command - not
# whenever it appears later as an argument to something else on the line.
_COMMAND_SEPARATORS = re.compile(r"&&|\|\||[;|]")

# A `python -m <module>` / `python3 -m <module>` / `py -m <module>` prefix,
# stripped before matching a tool name so `python -m pytest tests -q` is
# still recognized as a pytest invocation.
_MODULE_INVOCATION_PREFIX = re.compile(r"^(?:python3?|py)\s+-m\s+")


def tool_run_targets(
    workflow: dict, command_pattern: re.Pattern, skip_tokens=frozenset()
):
    """Return the scan targets a tool's `run:` invocations resolve to, or None.

    Each target is a `("dir", path)` pair (matched by prefix against a
    tracked file's path) or a `("glob", pattern)` pair (matched by
    fnmatch), resolved relative to the workflow's checkout root using each
    step's working-directory. A bare invocation with no non-flag/non-skipped
    arguments (`pytest`, `ruff check .`) falls back to a directory target at
    the step's own working-directory, since that is the tree it implicitly
    covers. Returns None when command_pattern never matches any `run:` text
    in the workflow at all, distinct from an empty target list (which cannot
    occur here, but mirrors shellcheck_targets' None-vs-empty contract:
    None means "no such step", a real list means "step(s) exist, check
    whether any of them covers this path").

    A run line is split into individual `&&`/`||`/`;`/`|`-separated command
    segments, and command_pattern is only accepted as a real invocation when
    it matches at the START of a segment (after stripping an optional
    `python -m` prefix) - not merely anywhere later in the line. Without this,
    a shared install line like `pip install ruff==0.15.15 pytest` reads both
    "ruff" and "pytest" as invocations of those tools and produces junk
    targets (`('glob', '==0.15.15')`, a bare `('dir', <working_directory>)`
    for "pytest") that happen to be harmless today only because they are
    permissive, not because they are correct - the same shape of bug #36 is
    about, just waiting for a real gap to hide behind one.
    """
    targets = []
    found = False
    for working_directory, step in iter_workflow_steps(workflow):
        run = step.get("run") or ""
        if not isinstance(run, str):
            continue
        for line in run.splitlines():
            for segment in _COMMAND_SEPARATORS.split(line):
                segment = segment.strip()
                if not segment:
                    continue
                invocation = _MODULE_INVOCATION_PREFIX.sub("", segment, count=1)
                match = command_pattern.match(invocation)
                if not match:
                    continue
                found = True
                tokens = [
                    token
                    for token in invocation[match.end() :].split()
                    if not token.startswith("-") and token not in skip_tokens
                ]
                if not tokens:
                    targets.append(("dir", working_directory))
                    continue
                for token in tokens:
                    kind, value = _classify_token(token)
                    targets.append(
                        (kind, join_relative_directory(working_directory, value))
                    )
    return targets if found else None


def path_is_covered(targets, relative_path: str) -> bool:
    """Return True if any (kind, value) target actually covers relative_path."""
    for kind, value in targets:
        if kind == "dir":
            if (
                not value
                or relative_path == value
                or relative_path.startswith(f"{value}/")
            ):
                return True
        elif fnmatch.fnmatch(relative_path, value):
            return True
    return False


def shellcheck_targets(workflow: dict):
    """Return the shellcheck scan targets configured in a workflow, or None.

    Combines directory targets from `uses: *shellcheck*` action steps
    (reading their `scandir`/`path` input) with the targets `tool_run_targets`
    resolves from any `run: shellcheck ...` command lines. Returns None only
    when neither form of shellcheck step is present at all; see
    tool_run_targets for the None-vs-empty-list contract this mirrors.
    """
    action_targets = []
    action_found = False
    for working_directory, step in iter_workflow_steps(workflow):
        uses = step.get("uses") or ""
        if isinstance(uses, str) and "shellcheck" in uses.lower():
            action_found = True
            with_block = step.get("with") or {}
            scandir = with_block.get("scandir") or with_block.get("path")
            directory = (
                join_relative_directory(working_directory, str(scandir))
                if scandir
                else working_directory
            )
            action_targets.append(("dir", directory))
    run_targets = tool_run_targets(workflow, _SHELLCHECK_STEP)
    if not action_found and run_targets is None:
        return None
    return action_targets + (run_targets or [])
