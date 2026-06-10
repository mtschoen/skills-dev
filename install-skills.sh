#!/usr/bin/env bash
# Install skills from this repo into one or more agent config dirs.
#
# Each top-level dir here is a skill submodule with a SKILL.md at its root.
# The installer ships only GIT-TRACKED files (via `git ls-files`), filtered to
# a top-level allowlist: SKILL.md + scripts/ + references/ + assets/, plus any
# extra top-level entries listed in the skill's optional `.skillpack` manifest.
# Shipping tracked files only means generated junk (e.g. __pycache__) can never
# leak from source. Each install is a true mirror of a clean staging tree, so
# files left in the destination by older installs are removed -- EXCEPT
# content created in the DEST by running installed scripts (__pycache__,
# *.pyc, .pytest_cache, and skill output dirs like reports/), which is
# preserved and never reported as drift (see IGNORE_PATTERNS below).
#
# Usage: ./install-skills.sh [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
#   -y / --yes       overwrite without prompting
#   -n / --dry-run   show what would change, don't copy
#   --agents         install to ~/.agents/skills (canonical source of truth)
#   --claude         install to ~/.claude/skills (Claude's mirror of ~/.agents/skills)
#   --gemini         install to ~/.gemini/config/skills (Antigravity's global skills dir)
#   --all            install to all known agent skill dirs
#   positional args  limit to specific skill names (default: all)
#
# With no agent flag, installs only to harness dirs that ALREADY EXIST on this
# machine, among ~/.agents/skills (canonical), ~/.claude/skills (Claude), and
# ~/.gemini/config/skills (Antigravity). A destination whose parent harness dir (e.g.
# ~/.gemini) is absent is skipped, so harnesses you don't use get no phantom
# dir. Pass an explicit --agents/--claude/--gemini/--all to create a missing
# one. Codex reads ~/.agents/skills natively, so it needs no copy.
#
# Test seam: set SKILLS_SRC_ROOT to override the source dir scanned for skills.

set -euo pipefail

SRC_ROOT="${SKILLS_SRC_ROOT:-"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"}"

ASSUME_YES=0
DRY_RUN=0
DEFAULT_MODE=0
ABORT=0
SELECTED=()
DESTINATIONS=()

# Baseline top-level entries shipped for every skill (Agent Skills convention
# + the required SKILL.md). Extra entries come from each skill's .skillpack.
BASELINE_INCLUDES=(SKILL.md scripts references assets)

# Destination content to preserve across installs: generated junk plus skill
# output dirs (e.g. cost-estimator writes reports/ next to its SKILL.md).
# Excluded from both the diff preview and the mirror apply, so it is never
# reported as drift and never deleted. No skill may SHIP a top-level entry
# with one of these names (it would be skipped on install).
IGNORE_PATTERNS=(__pycache__ '*.pyc' '*.pyo' .pytest_cache reports)

# Mirror $1 -> $2, deleting destination files absent from source but preserving
# IGNORE_PATTERNS. Prefers rsync (surgical). Without rsync, the old destination
# is moved aside, the fresh copy laid down, and IGNORE_PATTERNS entries restored
# from the old tree -- dest-only output like reports/ must survive either path.
mirror_tree() {
    local from="$1" to="$2" p
    if command -v rsync >/dev/null 2>&1; then
        local -a rexcl=()
        for p in "${IGNORE_PATTERNS[@]}"; do rexcl+=(--exclude="$p"); done
        mkdir -p "$to"
        rsync -a --delete "${rexcl[@]}" "$from/" "$to/"
        return
    fi
    local backup=""
    if [ -d "$to" ]; then
        backup="${to}.preserve.$$"
        rm -rf "$backup"
        mv "$to" "$backup"
    else
        rm -rf "$to"
    fi
    mkdir -p "$to"
    cp -a "$from/." "$to/"
    if [ -n "$backup" ]; then
        local f rel
        for p in "${IGNORE_PATTERNS[@]}"; do
            while IFS= read -r -d '' f; do
                rel="${f#"$backup"/}"
                if [ ! -e "$to/$rel" ]; then
                    mkdir -p "$(dirname "$to/$rel")"
                    cp -a "$f" "$to/$rel"
                fi
            done < <(find "$backup" -name "$p" -print0 2>/dev/null)
        done
        rm -rf "$backup"
    fi
}

add_destination() {
    local name="$1" path="$2"
    local existing
    for existing in "${DESTINATIONS[@]+"${DESTINATIONS[@]}"}"; do
        [ "$existing" = "$name|$path" ] && return 0
    done
    DESTINATIONS+=("$name|$path")
}

add_all_destinations() {
    maybe_add_destination agents "${HOME}/.agents/skills"
    maybe_add_destination claude "${HOME}/.claude/skills"
    maybe_add_destination gemini "${HOME}/.gemini/config/skills"
}

# Add a destination, but in default mode (no explicit agent flag) skip it when
# its parent harness dir (e.g. ~/.gemini) is absent, so harnesses you don't use
# get no phantom skills dir. Explicit flags bypass this by calling
# add_destination directly, so they always create.
maybe_add_destination() {
    local name="$1" path="$2" harness
    harness="$(dirname "$path")"
    if [ "$DEFAULT_MODE" = 1 ] && [ ! -d "$harness" ]; then
        echo "skip $name (harness dir $harness not present; pass --$name or --all to create)"
        return 0
    fi
    add_destination "$name" "$path"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes) ASSUME_YES=1; shift ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        --agents) add_destination agents "${HOME}/.agents/skills"; shift ;;
        --claude) add_destination claude "${HOME}/.claude/skills"; shift ;;
        --gemini) add_destination gemini "${HOME}/.gemini/config/skills"; shift ;;
        --all) add_all_destinations; shift ;;
        -h|--help)
            sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) echo "unknown flag: $1" >&2; exit 2 ;;
        *) SELECTED+=("$1"); shift ;;
    esac
done

if [ "${#DESTINATIONS[@]}" -eq 0 ]; then
    DEFAULT_MODE=1
    add_all_destinations
fi

if [ "${#DESTINATIONS[@]}" -eq 0 ]; then
    echo "No existing skill destinations on this machine. Pass --agents/--claude/--gemini or --all to bootstrap one."
    exit 0
fi

has_selection() { [ "${#SELECTED[@]}" -gt 0 ]; }
is_selected() {
    local name="$1"
    if ! has_selection; then return 0; fi
    local s
    for s in "${SELECTED[@]}"; do [ "$s" = "$name" ] && return 0; done
    return 1
}

# Extra top-level includes from <skill>/.skillpack (one per line; # comments;
# trailing slash and surrounding whitespace ignored). Prints normalized entries.
manifest_includes() {
    local manifest="$1/.skillpack"
    [ -f "$manifest" ] || return 0
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line//[[:space:]]/}"
        line="${line%/}"
        [ -n "$line" ] && printf '%s\n' "$line"
    done < "$manifest"
}

# Build a clean staging tree of shippable files for one skill: only git-tracked
# paths whose top-level component is in the include set, copied from the working
# tree (so uncommitted edits install). Untracked junk is never a candidate.
build_staging() {
    local src="$1" staging="$2"
    local -a includes=("${BASELINE_INCLUDES[@]}")
    local entry
    while IFS= read -r entry; do includes+=("$entry"); done < <(manifest_includes "$src")

    local f top hit
    while IFS= read -r f; do
        top="${f%%/*}"
        hit=0
        for entry in "${includes[@]}"; do
            if [ "$entry" = "$top" ]; then hit=1; break; fi
        done
        [ "$hit" = 1 ] || continue
        [ -e "$src/$f" ] || continue        # tracked but deleted in working tree
        mkdir -p "$staging/$(dirname "$f")"
        cp -p "$src/$f" "$staging/$f"
    done < <(git -C "$src" ls-files)
}

confirm() {
    local prompt="$1"
    if [ "$ASSUME_YES" = 1 ]; then return 0; fi
    local reply
    if [ -r /dev/tty ]; then
        read -r -p "$prompt [y/N/q=quit] " reply </dev/tty
    elif [ -t 0 ]; then
        read -r -p "$prompt [y/N/q=quit] " reply
    else
        echo "  (no tty; skipping. re-run with -y to overwrite.)" >&2
        return 1
    fi
    case "$reply" in
        [Qq]) ABORT=1; return 1 ;;
        [Yy]) return 0 ;;
        *) return 1 ;;
    esac
}

# Translate `diff -rq STAGING DEST` output into a git-status-style preview,
# stripping the absolute staging/dest prefixes (staging lives in a temp dir,
# which reads like a bug otherwise) down to skill-relative paths:
#   + path (new)                     shipped but not yet installed
#   ~ path (changed)                 present in both, contents differ
#   - path (removed, no longer shipped)  installed but no longer shipped
format_diff() {
    local staging="$1" dest="$2" line first rest dir name full
    while IFS= read -r line; do
        case "$line" in
            "Files "*" differ")
                first="${line#Files }"
                first="${first%% and *}"
                printf '  ~ %s (changed)\n' "${first#"$staging"/}"
                ;;
            "Only in "*)
                rest="${line#Only in }"
                dir="${rest%%: *}"
                name="${rest#*: }"
                full="$dir/$name"
                case "$full" in
                    "$staging"/*) printf '  + %s (new)\n' "${full#"$staging"/}" ;;
                    "$dest"/*)    printf '  - %s (removed, no longer shipped)\n' "${full#"$dest"/}" ;;
                esac
                ;;
        esac
    done
}

install_skill_to_destination() {
    local name="$1" agent="$2" dest_root="$3"
    local src="$SRC_ROOT/$name"
    if [ ! -f "$src/SKILL.md" ]; then
        echo "skip $name (no SKILL.md)"
        return
    fi

    local dest="$dest_root/$name"
    local staging
    staging="$(mktemp -d "${TMPDIR:-/tmp}/skillinst.XXXXXX")"
    build_staging "$src" "$staging"

    if [ ! -e "$dest" ]; then
        echo "install $name -> $dest ($agent)"
        if [ "$DRY_RUN" != 1 ]; then
            mirror_tree "$staging" "$dest"
        fi
        rm -rf "$staging"
        return
    fi

    local diff_out p
    local -a diff_excl=()
    for p in "${IGNORE_PATTERNS[@]}"; do diff_excl+=(-x "$p"); done
    diff_out="$(diff -rq "${diff_excl[@]}" "$staging" "$dest" 2>&1 || true)"
    if [ -z "$diff_out" ]; then
        echo "unchanged $name ($agent)"
        rm -rf "$staging"
        return
    fi

    echo
    echo "update $name -> $dest ($agent)"
    printf '%s\n' "$diff_out" | format_diff "$staging" "$dest"

    if [ "$DRY_RUN" = 1 ]; then
        echo "  (dry-run; not applying)"
        rm -rf "$staging"
        return
    fi

    if confirm "overwrite $dest?"; then
        mirror_tree "$staging" "$dest"
        echo "  updated."
    else
        echo "  skipped."
    fi
    rm -rf "$staging"
}

install_skill() {
    local name="$1" destination agent dest_root
    for destination in "${DESTINATIONS[@]}"; do
        [ "$ABORT" = 1 ] && break
        agent="${destination%%|*}"
        dest_root="${destination#*|}"
        install_skill_to_destination "$name" "$agent" "$dest_root"
    done
}

found=0
for src in "$SRC_ROOT"/*/; do
    [ "$ABORT" = 1 ] && break
    name="$(basename "$src")"
    [ -e "$src/.git" ] || continue       # only git submodules / repos
    found=$((found + 1))
    is_selected "$name" || continue
    install_skill "$name"
done

if [ "$found" = 0 ]; then
    echo "warning: no skill submodules found under $SRC_ROOT." >&2
    echo "         did you forget to run 'git submodule update --init --recursive'?" >&2
    exit 1
fi

if [ "$ABORT" = 1 ]; then
    echo
    echo "aborted by user (q); remaining skills skipped."
fi
