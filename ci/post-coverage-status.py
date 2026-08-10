#!/usr/bin/env python3
"""Post the pr-crew/coverage commit status from CI (stdlib only).

Computes line-coverage percent and POSTs it as a commit status
(context=pr-crew/coverage) on $GITHUB_SHA using the auto $GITHUB_TOKEN.
Works on both GitHub Actions and Gitea Actions: the API root comes from
GITHUB_API_URL, which each forge sets to its own base. The posting job needs
`permissions: statuses: write` on GitHub, where the default token is read-only.

Percent source:
  default                -> pytest-cov coverage.json ['totals']['percent_covered']
  --cobertura "<glob>"   -> merge Cobertura XML line hits across matched files
                            (a line counts covered if any report shows hits>0)

Set COVERAGE_STEP_OUTCOME to the coverage step's outcome. Any non-success or
measurement failure posts state=error (pr-crew then reads the gate as
'unreadable', not silently missing) and still exits 0 so an `if: always()` step
does not double-fail the job. A POST/network failure DOES raise.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import urllib.request
import xml.etree.ElementTree as ElementTree


def _percent_from_coverage_json(path: str) -> float:
    with open(path) as handle:
        return float(json.load(handle)["totals"]["percent_covered"])


def _is_build_output(path: str) -> bool:
    """True for a path inside a bin/ or obj/ directory, on any platform."""
    normalized = path.replace("\\", "/")
    return "/bin/" in normalized or "/obj/" in normalized


def _percent_from_cobertura(patterns: list[str]) -> float:
    # glob returns native separators, so a bare "/bin/" test silently matches
    # nothing on Windows and build output gets parsed as a coverage report.
    paths = [
        path
        for pattern in patterns
        for path in glob.glob(pattern, recursive=True)
        if not _is_build_output(path)
    ]
    if not paths:
        raise FileNotFoundError("no Cobertura XML matched")
    lines: dict[tuple[str, str], bool] = {}
    for path in paths:
        for class_node in ElementTree.parse(path).getroot().iter("class"):
            filename = class_node.get("filename", "")
            for line_node in class_node.iter("line"):
                key = (filename, line_node.get("number", ""))
                lines[key] = (
                    lines.get(key, False) or int(line_node.get("hits", "0")) > 0
                )
    if not lines:
        raise ValueError("no source lines in Cobertura XML")
    return 100.0 * sum(1 for covered in lines.values() if covered) / len(lines)


def _api_root() -> str:
    """Base URL for the statuses API, on either forge.

    Both GitHub Actions and Gitea Actions export GITHUB_API_URL already pointing
    at their own API root (https://api.github.com and <gitea>/api/v1
    respectively), so preferring it makes this script forge-agnostic. The
    fallback derives Gitea's layout from GITHUB_SERVER_URL for older runners
    that do not set GITHUB_API_URL. Hard-coding /api/v1 against GITHUB_SERVER_URL
    is what made this fail on GitHub with HTTP 410 Gone.
    """
    api_url = os.environ.get("GITHUB_API_URL")
    if api_url:
        return api_url.rstrip("/")
    return f"{os.environ['GITHUB_SERVER_URL'].rstrip('/')}/api/v1"


def _post(state: str, description: str) -> None:
    server = os.environ["GITHUB_SERVER_URL"]
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    body = json.dumps(
        {
            "context": "pr-crew/coverage",
            "state": state,
            "description": description,
            "target_url": f"{server}/{repository}/actions/runs/{run_id}",
        }
    ).encode()
    request = urllib.request.Request(
        f"{_api_root()}/repos/{repository}/statuses/{sha}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(request).read()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", default="coverage.json")
    parser.add_argument("--cobertura", nargs="+")
    arguments = parser.parse_args(argv[1:])
    coverage_step_outcome = os.environ.get("COVERAGE_STEP_OUTCOME", "success")
    if coverage_step_outcome != "success":
        print(
            f"coverage step did not succeed: {coverage_step_outcome}", file=sys.stderr
        )
        _post("error", "coverage step failed")
        return 0
    try:
        if arguments.cobertura:
            percent = _percent_from_cobertura(arguments.cobertura)
        else:
            percent = _percent_from_coverage_json(arguments.coverage_json)
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError(f"coverage percent out of range: {percent}")
    except Exception as error:  # measurement failed -> post error, exit 0
        print(f"coverage measurement failed: {error}", file=sys.stderr)
        _post("error", "coverage measurement failed")
        return 0
    percent = round(percent, 2)
    _post("success", f"{percent}% line coverage")
    print(f"posted pr-crew/coverage success: {percent}% line coverage")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
