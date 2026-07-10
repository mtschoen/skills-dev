#!/usr/bin/env python3
"""Configure dual-host pushes for skills-dev and every skill submodule.

``git push origin`` must update BOTH canonical hosts, so gitea and github
cannot drift apart (they did through 2026-07: wrap and skills-dev each
accumulated commits the other host never saw). This sets two explicit
``remote.origin.pushurl`` values per repo, derived from the repo basename
of the origin fetch URL, so it works regardless of which host the clone
came from. Idempotent; re-run any time (e.g. after adding a submodule).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITEA_PUSH = "gitea@llamabox.sticktoitive.net:schoen/{}.git"
GITHUB_PUSH = "git@github.com:mtschoen/{}.git"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def submodule_paths() -> list[Path]:
    out = git(
        ROOT, "config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.path"
    )
    return [ROOT / line.split(" ", 1)[1] for line in out.splitlines()]


def configure(repo: Path) -> str:
    basename = git(repo, "remote", "get-url", "origin").rstrip("/").rsplit("/", 1)[-1]
    basename = basename.rsplit(":", 1)[-1].removesuffix(".git")
    subprocess.run(
        ["git", "-C", str(repo), "config", "--unset-all", "remote.origin.pushurl"],
        capture_output=True,
        check=False,  # exit 5 = nothing to unset on a fresh clone
    )
    for template in (GITEA_PUSH, GITHUB_PUSH):
        git(repo, "config", "--add", "remote.origin.pushurl", template.format(basename))
    return basename


def main() -> int:
    failures = []
    for repo in [ROOT, *submodule_paths()]:
        if not (repo / ".git").exists():
            print(f"skip {repo.name} (submodule not initialized)")
            continue
        try:
            basename = configure(repo)
        except subprocess.CalledProcessError as exc:
            failures.append(repo.name)
            print(f"FAIL {repo.name}: {exc.stderr.strip()}", file=sys.stderr)
            continue
        print(f"ok   {repo.name} -> {basename} (pushes to gitea + github)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
