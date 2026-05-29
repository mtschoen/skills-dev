#!/usr/bin/env python3
"""PostToolUse on-save linter for skills-dev.

Reads the Claude Code PostToolUse hook payload from stdin, and if the edited
file is Python (ruff) or shell (shellcheck, when available), runs the linter
and surfaces any findings back to the session as additionalContext. Advisory
only: this hook never blocks an edit and always exits 0. The authoritative
gate is `ruff check scripts/ tests/` (tier 2) and CI (tier 3).

Written in Python rather than the LINTER-SETUP.md inline-bash form so it runs
identically regardless of which shell Claude Code uses on Windows vs. Unix,
and without a jq dependency.
"""

import contextlib
import json
import shutil
import subprocess
import sys


def lint(file_path):
    """Return (tool_name, findings_text) for a file, or None if nothing to say."""
    if file_path.endswith(".py"):
        ruff = shutil.which("ruff")
        if not ruff:
            return None
        result = subprocess.run(
            [ruff, "check", file_path], capture_output=True, text=True
        )
        out = (result.stdout + result.stderr).strip()
        return ("ruff", out) if out and result.returncode != 0 else None
    if file_path.endswith(".sh"):
        shellcheck = shutil.which("shellcheck")
        if not shellcheck:
            return None
        result = subprocess.run(
            [shellcheck, file_path], capture_output=True, text=True
        )
        out = (result.stdout + result.stderr).strip()
        return ("shellcheck", out) if out and result.returncode != 0 else None
    return None


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
    result = lint(file_path)
    if not result:
        return
    tool, findings = result
    context = f"{tool} findings on {file_path} (on-save lint, advisory):\n{findings}"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    # Never let a linter hiccup break the session.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
