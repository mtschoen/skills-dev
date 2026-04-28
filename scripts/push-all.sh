#!/usr/bin/env bash
# Push every active submodule + skills-dev itself to both `origin` (Gitea)
# and `github` (GitHub). Errors are printed inline and don't halt the run —
# one bad push won't block the rest.
#
# Run from anywhere; the script cd's to the repo root.

cd "$(dirname "$0")/.."

push_one() {
  local dir=$1 remote=$2
  if git -C "$dir" remote 2>/dev/null | grep -qx "$remote"; then
    echo "  -> $remote"
    git -C "$dir" push "$remote" main || echo "  FAILED: $dir -> $remote"
  fi
}

while IFS= read -r path; do
  echo "=== $path ==="
  if [ -e "$path/.git" ]; then
    push_one "$path" origin
    push_one "$path" github
  else
    echo "  (not initialized, skipping)"
  fi
done < <(git config --file .gitmodules --get-regexp 'submodule\..*\.path' | awk '{print $2}')

echo "=== skills-dev (index) ==="
push_one "." origin
push_one "." github
