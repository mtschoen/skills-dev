#!/usr/bin/env bash
# Fetch + fast-forward main from `origin` and optionally one additional remote
# named with `--remote <name>` in every active submodule and the skills-dev
# index. Does not bump submodule pointers — `git add` and commit those manually
# if you want them recorded in the index.
#
# Run from anywhere; the script cd's to the repo root.

cd "$(dirname "$0")/.."

remotes=(origin)

usage() {
  cat <<'EOF'
Usage: scripts/pull-all.sh [--remote <name>]

Fetch + fast-forward main from origin in every active submodule plus skills-dev
itself. If --remote is provided, also fetch + fast-forward from that remote
where it exists.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --remote)
      [ $# -ge 2 ] || { echo "--remote requires a value" >&2; exit 2; }
      remotes+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

pull_one() {
  local dir=$1 remote=$2
  if ! git -C "$dir" remote get-url "$remote" >/dev/null 2>&1; then
    return
  fi
  echo "=== $dir ($remote) ==="
  git -C "$dir" fetch "$remote" || { echo "  FAILED: fetch"; return; }
  git -C "$dir" merge --ff-only "$remote/main" || echo "  (not fast-forwardable; resolve manually)"
}

while IFS= read -r path; do
  if [ -e "$path/.git" ]; then
    for remote in "${remotes[@]}"; do
      pull_one "$path" "$remote"
    done
  else
    echo "=== $path (not initialized, skipping) ==="
  fi
done < <(git config --file .gitmodules --get-regexp 'submodule\..*\.path' | awk '{print $2}')

for remote in "${remotes[@]}"; do
  pull_one "." "$remote"
done
