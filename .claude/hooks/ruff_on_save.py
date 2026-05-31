#!/usr/bin/env python3
"""PostToolUse on-save linter for skills-dev.

Reads the Claude Code PostToolUse hook payload from stdin and lints the edited
file, surfacing any findings back to the session as additionalContext. Advisory
only: this hook never blocks an edit and always exits 0. The authoritative
gates are the tier-2 commands (`ruff check`, `shellcheck`, `markdownlint-cli2`,
`python scripts/validate_skills.py`) and CI (tier 3).

Per file type:
  *.py      -> ruff check
  *.sh      -> shellcheck (when installed)
  *.md      -> markdownlint-cli2 (respects the nearest .markdownlint-cli2.jsonc)
  SKILL.md  -> additionally `agentskills validate <skill-dir>` (skills-ref spec)

Written in Python rather than the LINTER-SETUP.md inline-bash form so it runs
identically regardless of which shell Claude Code uses on Windows vs. Unix, and
without a jq dependency. Node CLIs (markdownlint-cli2) installed as Windows
`.cmd` shims are launched via `cmd /c` because CreateProcess cannot start a
batch file directly.

Every linter invocation is timed and appended to the hook-timing log (see
`_TIMING_LOG`); `scripts/hook-timing.py` aggregates it so the per-edit overhead
of each tool is measurable, not guessed.
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_TIMING_LOG = Path.home() / ".cache" / "skills-dev" / "hook-timing.jsonl"


def _record(tool, file_path, elapsed_ms, exit_code):
    """Append one timing sample to the hook-timing log. Best-effort; never raises."""
    with contextlib.suppress(Exception):
        _TIMING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _TIMING_LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "tool": tool,
                        "file": file_path,
                        "ms": round(elapsed_ms, 1),
                        "exit": exit_code,
                    }
                )
                + "\n"
            )


def _run(tool, file_path, executable, *args):
    """Run a linter, recording its wall time. Returns (combined_output, returncode).

    On Windows a `.cmd`/`.bat` shim (e.g. a global npm bin) cannot be launched
    directly by CreateProcess, so route it through `cmd /c`.
    """
    command = [executable, *args]
    if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]
    start = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True)
    _record(tool, file_path, (time.perf_counter() - start) * 1000, result.returncode)
    return (result.stdout + result.stderr).strip(), result.returncode


def lint(file_path):
    """Return a list of (tool_name, findings_text) for a file ([] if clean)."""
    findings = []
    if file_path.endswith(".py"):
        ruff = shutil.which("ruff")
        if ruff:
            out, code = _run("ruff", file_path, ruff, "check", file_path)
            if out and code != 0:
                findings.append(("ruff", out))
    elif file_path.endswith(".sh"):
        shellcheck = shutil.which("shellcheck")
        if shellcheck:
            out, code = _run("shellcheck", file_path, shellcheck, file_path)
            if out and code != 0:
                findings.append(("shellcheck", out))
    elif file_path.endswith(".md"):
        markdownlint = shutil.which("markdownlint-cli2")
        if markdownlint:
            # --no-globs + the ':' literal-path prefix scope the lint to just the
            # edited file. Without them, the repo's .markdownlint-cli2.jsonc globs
            # are merged in and cli2 re-lints the whole tree (~65 files) on every
            # save, reporting findings from unrelated files. Rules still apply.
            out, code = _run("markdownlint", file_path, markdownlint, "--no-globs", f":{file_path}")
            if out and code != 0:
                findings.append(("markdownlint", out))
        # A SKILL.md additionally gets Agent Skills spec validation (frontmatter,
        # naming, field rules) — markdownlint does not cover that.
        if os.path.basename(file_path) == "SKILL.md":
            agentskills = shutil.which("agentskills")
            if agentskills:
                skill_dir = os.path.dirname(file_path) or "."
                out, code = _run("skillref", file_path, agentskills, "validate", skill_dir)
                if out and code != 0:
                    findings.append(("skillref (agentskills validate)", out))
    return findings


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    file_path = tool_input.get("file_path") or tool_response.get("filePath")
    if not file_path:
        return
    results = lint(file_path)
    if not results:
        return
    blocks = [
        f"{tool} findings on {file_path} (on-save lint, advisory):\n{findings}"
        for tool, findings in results
    ]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(blocks),
                }
            }
        )
    )


if __name__ == "__main__":
    # Never let a linter hiccup break the session.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
