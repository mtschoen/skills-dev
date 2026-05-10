#!/usr/bin/env bash
# Push every active submodule + skills-dev itself to both `origin` (Gitea)
# and `github` (GitHub). Each push is pre-flighted: fetch the remote and
# classify local main vs remote/main as up-to-date / FF / behind / diverged.
# A non-FF state is reported with a clear reason instead of a generic
# "FAILED" line. Errors don't halt the run, but the script exits non-zero
# with a summary if any push had a problem.
#
# Run from anywhere; the script cd's to the repo root.

cd "$(dirname "$0")/.."

failures=()

push_one() {
  local dir=$1 remote=$2
  if ! git -C "$dir" remote get-url "$remote" >/dev/null 2>&1; then
    return
  fi
  echo "  -> $remote"
  if ! git -C "$dir" fetch "$remote" --quiet 2>/dev/null; then
    echo "     fetch failed (network/auth)"
    failures+=("$dir -> $remote (fetch failed)")
    return
  fi
  local counts ahead behind
  counts=$(git -C "$dir" rev-list --left-right --count "main...refs/remotes/$remote/main" 2>/dev/null)
  if [ -z "$counts" ]; then
    echo "     could not compare local main with $remote/main"
    failures+=("$dir -> $remote (compare failed)")
    return
  fi
  read -r ahead behind <<<"$counts"
  if [ "$ahead" = "0" ] && [ "$behind" = "0" ]; then
    echo "     up-to-date"
    return
  fi
  if [ "$ahead" = "0" ]; then
    echo "     behind by $behind (skipping push; pull first)"
    failures+=("$dir -> $remote (behind by $behind)")
    return
  fi
  if [ "$behind" != "0" ]; then
    echo "     DIVERGED: ahead $ahead, behind $behind (skipping push; merge first)"
    failures+=("$dir -> $remote (diverged: ahead $ahead, behind $behind)")
    return
  fi
  if ! git -C "$dir" push "$remote" main; then
    failures+=("$dir -> $remote (push failed)")
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

echo
echo "=== Summary ==="
if [ ${#failures[@]} -eq 0 ]; then
  echo "All pushes succeeded or already up-to-date."
  exit 0
fi
echo "${#failures[@]} issue(s):"
for f in "${failures[@]}"; do
  echo "  $f"
done
exit 1
