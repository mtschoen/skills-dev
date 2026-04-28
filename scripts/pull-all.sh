#!/usr/bin/env bash
# Fetch + fast-forward main from `origin` (Gitea) in every active submodule
# and the skills-dev index. Does not bump submodule pointers — `git add`
# and commit those manually if you want them recorded in the index.
#
# Run from anywhere; the script cd's to the repo root.

cd "$(dirname "$0")/.."

pull_one() {
  local dir=$1
  echo "=== $dir ==="
  git -C "$dir" fetch origin || { echo "  FAILED: fetch"; return; }
  git -C "$dir" merge --ff-only origin/main || echo "  (not fast-forwardable; resolve manually)"
}

while IFS= read -r path; do
  if [ -e "$path/.git" ]; then
    pull_one "$path"
  else
    echo "=== $path (not initialized, skipping) ==="
  fi
done < <(git config --file .gitmodules --get-regexp 'submodule\..*\.path' | awk '{print $2}')

pull_one "."
