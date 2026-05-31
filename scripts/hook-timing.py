#!/usr/bin/env python3
"""Aggregate the on-save hook timing log into per-tool overhead stats.

The PostToolUse linter hook (`.claude/hooks/ruff_on_save.py`) appends one JSON
line per linter invocation to `~/.cache/skills-dev/hook-timing.jsonl`. This
reports how much wall-clock each tool adds per edit, so on-save linting overhead
is measured rather than guessed.

Usage:
  python scripts/hook-timing.py              # summary over the whole log
  python scripts/hook-timing.py --recent 50  # only the last 50 samples
  python scripts/hook-timing.py --reset      # truncate the log
"""

import argparse
import json
from pathlib import Path

LOG = Path.home() / ".cache" / "skills-dev" / "hook-timing.jsonl"


def percentile(values, pct):
    """Linear-interpolated percentile of a list of numbers."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def load(recent=None):
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-recent:] if recent else rows


def main():
    parser = argparse.ArgumentParser(description="Aggregate on-save hook timing.")
    parser.add_argument("--recent", type=int, metavar="N", help="only the last N samples")
    parser.add_argument("--reset", action="store_true", help="truncate the timing log")
    args = parser.parse_args()

    if args.reset:
        if LOG.exists():
            LOG.unlink()
        print(f"reset {LOG}")
        return

    rows = load(args.recent)
    if not rows:
        print(f"no timing samples in {LOG}")
        return

    by_tool = {}
    for row in rows:
        by_tool.setdefault(row.get("tool", "?"), []).append(float(row.get("ms", 0)))

    name_width = max(len(tool) for tool in by_tool)
    header = (
        f"{'tool':<{name_width}}  {'n':>5}  {'total_s':>8}  "
        f"{'mean_ms':>8}  {'p50':>7}  {'p95':>7}  {'max':>7}"
    )
    print(header)
    print("-" * len(header))

    grand_total = 0.0
    grand_n = 0
    for tool in sorted(by_tool, key=lambda t: -sum(by_tool[t])):
        samples = by_tool[tool]
        total = sum(samples)
        grand_total += total
        grand_n += len(samples)
        print(
            f"{tool:<{name_width}}  {len(samples):>5}  {total / 1000:>8.2f}  "
            f"{total / len(samples):>8.1f}  {percentile(samples, 50):>7.1f}  "
            f"{percentile(samples, 95):>7.1f}  {max(samples):>7.1f}"
        )

    print("-" * len(header))
    print(
        f"{'ALL':<{name_width}}  {grand_n:>5}  {grand_total / 1000:>8.2f}  "
        f"{grand_total / grand_n:>8.1f}"
    )
    print(f"\nlog: {LOG}  ({len(rows)} samples shown)")


if __name__ == "__main__":
    main()
