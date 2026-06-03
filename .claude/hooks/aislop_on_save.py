#!/usr/bin/env python3
"""PostToolUse aislop gate for skills-dev, scoped to code-file edits.

aislop scores the WHOLE repo on every run (no diff/single-file mode), so firing
it on every edit costs ~1.9s regardless of what changed. This wrapper only
invokes aislop when the edited file is a source file in a language aislop scores
(.py/.ts/.js/.go/.rs/.rb/.php/.java/.cs/...), skipping markdown/shell/doc edits
where aislop has nothing to say.

It reads the PostToolUse payload from stdin, forwards the same bytes to
`aislop hook claude` when in scope, passes aislop's additionalContext through
unchanged, and records its wall time to the shared hook-timing log
(see scripts/hook-timing.py). Advisory only: always exits 0.
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
_AISLOP_VERSION = "0.9.4"

# Languages aislop actually scores. Markdown/shell are outside its scope, so an
# edit to those should not trigger a whole-repo rescan.
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".rb", ".php", ".java", ".cs",
}


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


def main():
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    file_path = tool_input.get("file_path") or tool_response.get("filePath")
    if not file_path:
        return
    if os.path.splitext(file_path)[1].lower() not in CODE_EXTENSIONS:
        return  # docs/markdown/shell edit — skip the whole-repo aislop scan

    npx = shutil.which("npx")
    if not npx:
        return
    command = [npx, "-y", f"aislop@{_AISLOP_VERSION}", "hook", "claude"]
    if os.name == "nt" and npx.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    start = time.perf_counter()
    result = subprocess.run(command, input=raw, capture_output=True, cwd=project_dir)
    _record("aislop", file_path, (time.perf_counter() - start) * 1000, result.returncode)
    # Forward aislop's stdout (its additionalContext JSON, if any) unchanged.
    sys.stdout.buffer.write(result.stdout)


if __name__ == "__main__":
    # Never let the aislop hook break the session.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
