#!/usr/bin/env bash
# Install skills from this repo into ~/.claude/skills/.
#
# Each top-level dir here is a skill submodule. The installable content is
# either `<skill>/skill-draft/` (legacy layout) or `<skill>/` itself (new
# layout, detected by a SKILL.md at the root). Dev-only files are excluded
# for the root layout.
#
# Usage: ./install-skills.sh [-y] [-n] [skill ...]
#   -y / --yes       overwrite without prompting
#   -n / --dry-run   show what would change, don't copy
#   positional args  limit to specific skill names (default: all)

set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_ROOT="${HOME}/.claude/skills"

ASSUME_YES=0
DRY_RUN=0
SELECTED=()

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes) ASSUME_YES=1; shift ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) echo "unknown flag: $1" >&2; exit 2 ;;
        *) SELECTED+=("$1"); shift ;;
    esac
done

# Files/dirs excluded when installing from a skill's root (new layout).
# The skill-draft/ layout already isolates installable content, so these
# aren't applied there.
ROOT_EXCLUDES=(
    .git .gitignore .gitmodules .github
    README.md AUDIT.md LICENSE HANDOFF.md
    docs evals hooks node_modules reports
    skill-draft
)

has_selection() { [ "${#SELECTED[@]}" -gt 0 ]; }
is_selected() {
    local name="$1"
    if ! has_selection; then return 0; fi
    local s
    for s in "${SELECTED[@]}"; do [ "$s" = "$name" ] && return 0; done
    return 1
}

# diff args for root-layout skills (honors ROOT_EXCLUDES on the source side).
diff_args_for() {
    local layout="$1"
    local args="-rq"
    if [ "$layout" = "root" ]; then
        local e
        for e in "${ROOT_EXCLUDES[@]}"; do
            args="$args --exclude=$e"
        done
    fi
    echo "$args"
}

# Copy content_dir -> dest, replacing dest entirely. Honors excludes for
# root layout via tar --exclude.
sync_dir() {
    local content_dir="$1" dest="$2" layout="$3"
    rm -rf "$dest"
    mkdir -p "$dest"
    local excl_args=()
    if [ "$layout" = "root" ]; then
        local e
        for e in "${ROOT_EXCLUDES[@]}"; do
            excl_args+=(--exclude="./$e")
        done
    fi
    tar -C "$content_dir" ${excl_args[@]+"${excl_args[@]}"} -cf - . | tar -C "$dest" -xf -
}

confirm() {
    local prompt="$1"
    if [ "$ASSUME_YES" = 1 ]; then return 0; fi
    local reply
    if [ -r /dev/tty ]; then
        read -r -p "$prompt [y/N] " reply </dev/tty
    elif [ -t 0 ]; then
        read -r -p "$prompt [y/N] " reply
    else
        echo "  (no tty; skipping. re-run with -y to overwrite.)" >&2
        return 1
    fi
    [[ "$reply" =~ ^[Yy]$ ]]
}

install_skill() {
    local name="$1"
    local src_dir="$SRC_ROOT/$name"
    local content_dir layout
    if [ -d "$src_dir/skill-draft" ]; then
        content_dir="$src_dir/skill-draft"
        layout="draft"
    elif [ -f "$src_dir/SKILL.md" ]; then
        content_dir="$src_dir"
        layout="root"
    else
        echo "skip $name (no SKILL.md and no skill-draft/)"
        return
    fi

    local dest="$DEST_ROOT/$name"

    if [ ! -e "$dest" ]; then
        echo "install $name -> $dest"
        if [ "$DRY_RUN" != 1 ]; then
            sync_dir "$content_dir" "$dest" "$layout"
        fi
        return
    fi

    # Existing install — detect changes.
    # shellcheck disable=SC2046
    local diff_out
    diff_out=$(diff $(diff_args_for "$layout") "$content_dir" "$dest" 2>&1 || true)
    if [ -z "$diff_out" ]; then
        echo "unchanged $name"
        return
    fi

    echo
    echo "update $name (changes below):"
    echo "$diff_out" | sed 's/^/  /'

    if [ "$DRY_RUN" = 1 ]; then
        echo "  (dry-run; not applying)"
        return
    fi

    if confirm "overwrite $dest?"; then
        sync_dir "$content_dir" "$dest" "$layout"
        echo "  updated."
    else
        echo "  skipped."
    fi
}

mkdir -p "$DEST_ROOT"

for src in "$SRC_ROOT"/*/; do
    name="$(basename "$src")"
    # Only top-level git submodules.
    [ -e "$src/.git" ] || continue
    is_selected "$name" || continue
    install_skill "$name"
done
