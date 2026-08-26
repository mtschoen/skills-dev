#!/usr/bin/env bash
# Install skills from this repo into one or more agent config dirs.
# Skill source repositories are authoritative; runtime destinations are generated
# mirrors and must not be edited directly.
#
# Each top-level dir here is a skill submodule with a SKILL.md at its root.
# The installer ships only GIT-TRACKED files (via `git ls-files`), filtered to
# a top-level allowlist: SKILL.md + scripts/ + references/ + assets/, plus any
# extra top-level entries listed in the skill's optional `.skillpack` manifest.
# Shipping tracked files only means generated junk (e.g. __pycache__) can never
# leak from source. Each install is a true mirror of a clean staging tree, so
# files left in the destination by older installs are removed -- EXCEPT
# content created in the DEST by running installed scripts (__pycache__,
# *.pyc, .pytest_cache), which is preserved and never reported as drift
# (see IGNORE_PATTERNS below).
#
# Usage: ./install-skills.sh [-y] [-n] [--check] [--agents] [--claude] [--gemini] [--hermes] [--all] [--setup-debuggers] [--hooks] [--prune-hooks] [skill ...]
#   -y / --yes         overwrite without prompting
#   -n / --dry-run     show what would change, don't copy
#   --check            check for drift without prompting or writing (0 clean, 1 drift, 2 argument error)
#   --agents           install to ~/.agents/skills (canonical source of truth)
#   --claude           install to ~/.claude/skills (Claude's mirror of ~/.agents/skills)
#   --gemini           install to ~/.gemini/config/skills (Antigravity's global skills dir)
#   --hermes           install to Hermes home (HERMES_HOME, LOCALAPPDATA/hermes, or ~/.hermes)
#   --all              install to all known agent skill dirs
#   --setup-debuggers  after install, run using-a-debugger's setup-debuggers.py to
#                      install the debuggers it drives (netcoredbg/gdb/lldb/cdb,
#                      platform-gated, idempotent); honors -n as the script's --dry-run
#   --hooks            check and offer to register hooks in harness settings
#   --prune-hooks      prune dangling hook entries pointing to uninstalled skill files
#   positional args    limit to specific skill names (default: all)
#
# With no agent flag, installs only to harness dirs that ALREADY EXIST on this
# machine, among ~/.agents/skills (canonical), ~/.claude/skills (Claude),
# ~/.gemini/config/skills (Antigravity), and Hermes. A destination whose parent
# harness dir (e.g.
# ~/.gemini) is absent is skipped, so harnesses you don't use get no phantom
# dir. Pass an explicit --agents/--claude/--gemini/--hermes/--all to create a missing
# one. Codex reads ~/.agents/skills natively, so it needs no copy.
#
# Test seam: set SKILLS_SRC_ROOT to override the source dir scanned for skills.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="${SKILLS_SRC_ROOT:-"$REPO_DIR"}"

git_workdir_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s\n' "$1"
    fi
}

hermes_home() {
    local home
    if [ -n "${HERMES_HOME:-}" ]; then
        home="$HERMES_HOME"
    elif [ -n "${LOCALAPPDATA:-}" ] && [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
        home="$LOCALAPPDATA/hermes"
    else
        home="$HOME/.hermes"
    fi
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -u "$home"
    else
        printf '%s\n' "$home"
    fi
}

ASSUME_YES=0
DRY_RUN=0
CHECK_MODE=0
DRIFT_FOUND=0
DEFAULT_MODE=0
SETUP_DEBUGGERS=0
HOOKS_MODE=0
PRUNE_HOOKS=0
ABORT=0
APPLY_FAILED=0
SELECTED=()
DESTINATIONS=()

# Baseline top-level entries shipped for every skill (Agent Skills convention
# + the required SKILL.md). Extra entries come from each skill's .skillpack.
BASELINE_INCLUDES=(SKILL.md scripts references assets)

# Destination content to preserve across installs: generated junk created in
# the DEST by running installed scripts (Python caches). Excluded from both the
# diff preview and the mirror apply, so it is never reported as drift and never
# deleted. No skill may SHIP a top-level entry with one of these names (it would
# be skipped on install). Skills now write generated output OUTSIDE the install
# tree (e.g. cost-estimator uses ~/.claude/cost-estimator/), so reports/ no
# longer needs preserving here.
IGNORE_PATTERNS=(__pycache__ '*.pyc' '*.pyo' .pytest_cache)

# True when any component of destination-relative path $1 matches IGNORE_PATTERNS,
# so preserved caches are never pruned.
path_is_preserved() {
    local rel="$1" comp p
    while :; do
        comp="${rel##*/}"
        for p in "${IGNORE_PATTERNS[@]}"; do
            # shellcheck disable=SC2254  # $p is a glob pattern by design
            case "$comp" in
                $p) return 0 ;;
            esac
        done
        case "$rel" in
            */*) rel="${rel%/*}" ;;
            *) return 1 ;;
        esac
    done
}

# Delete entries under $2 that $1 no longer ships, plus any whose type changed
# (file <-> directory) so the copy that follows cannot fail on them.
prune_removed() {
    local from="$1" to="$2" f rel
    while IFS= read -r -d '' f; do
        [ -e "$f" ] || continue          # a parent was pruned already
        rel="${f#"$to"/}"
        path_is_preserved "$rel" && continue
        if [ -e "$from/$rel" ]; then
            [ -d "$f" ] && [ -d "$from/$rel" ] && continue
            [ ! -d "$f" ] && [ ! -d "$from/$rel" ] && continue
        fi
        rm -rf "$f" || return 1
    done < <(find "$to" -mindepth 1 -print0)
    return 0
}

# Mirror $1 -> $2, deleting destination files absent from source but preserving
# IGNORE_PATTERNS. Prefers rsync (surgical). The fallback syncs in place and must
# never rename $2: on Windows a running agent holds an open handle on installed
# skill directories, which fails the rename while leaving the contents writable.
# Returns non-zero on failure; callers MUST check, because errexit does not reach
# here -- install_skill invokes its caller as part of an || list, which disables
# it for the whole dynamic extent.
mirror_tree() {
    local from="$1" to="$2" p
    if command -v rsync >/dev/null 2>&1; then
        local -a rexcl=()
        for p in "${IGNORE_PATTERNS[@]}"; do rexcl+=(--exclude="$p"); done
        mkdir -p "$to" || return 1
        rsync -a --delete "${rexcl[@]}" "$from/" "$to/" || return 1
        return 0
    fi
    mkdir -p "$to" || return 1
    prune_removed "$from" "$to" || return 1
    cp -a "$from/." "$to/" || return 1
    return 0
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
    maybe_add_destination hermes "$(hermes_home)/skills"
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
        --check) CHECK_MODE=1; DRY_RUN=1; ASSUME_YES=1; shift ;;
        --agents) add_destination agents "${HOME}/.agents/skills"; shift ;;
        --claude) add_destination claude "${HOME}/.claude/skills"; shift ;;
        --gemini) add_destination gemini "${HOME}/.gemini/config/skills"; shift ;;
        --hermes) add_destination hermes "$(hermes_home)/skills"; shift ;;
        --all) add_all_destinations; shift ;;
        --setup-debuggers) SETUP_DEBUGGERS=1; shift ;;
        --hooks) HOOKS_MODE=1; shift ;;
        --prune-hooks) PRUNE_HOOKS=1; shift ;;
        -h|--help)
            sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'
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
    echo "No existing skill destinations on this machine. Pass --agents/--claude/--gemini/--hermes or --all to bootstrap one."
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

    local f git_src tracked top hit
    git_src="$(git_workdir_path "$src")"
    tracked="$(mktemp "${TMPDIR:-/tmp}/skillfiles.XXXXXX")"
    if ! git -C "$git_src" ls-files > "$tracked"; then
        if [ -e "$src/.git" ]; then
            echo "could not enumerate tracked files for $(basename "$src")" >&2
            rm -f "$tracked"
            return 1
        fi
        echo "skip $(basename "$src") (not a git worktree)"
        rm -f "$tracked"
        return 2
    fi
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
    done < "$tracked"
    rm -f "$tracked"
    if [ -z "$(ls -A "$staging")" ]; then
        return 2
    fi
}

confirm() {
    local prompt="$1"
    if [ "$ASSUME_YES" = 1 ]; then return 0; fi
    local reply
    if [ -r /dev/tty ]; then
        # -r can succeed while opening fails (e.g. detached agent shells); treat a
        # failed read as no tty rather than crashing on an unset reply.
        if ! read -r -p "$prompt [y/N/q=quit] " reply </dev/tty; then
            echo "  (no usable tty; skipping. re-run with -y to overwrite.)" >&2
            return 1
        fi
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
    local name="$1" src="$2" agent="$3" dest_root="$4"
    if [ ! -f "$src/SKILL.md" ]; then
        echo "skip $name (no SKILL.md)"
        return
    fi

    local dest="$dest_root/$name"
    local staging
    staging="$(mktemp -d "${TMPDIR:-/tmp}/skillinst.XXXXXX")"
    local build_status
    if build_staging "$src" "$staging"; then
        build_status=0
    else
        build_status=$?
    fi
    if [ "$build_status" -ne 0 ]; then
        rm -rf "$staging"
        [ "$build_status" -eq 2 ] && return
        return 1
    fi
    if [ ! -e "$staging" ] || [ -z "$(ls -A "$staging")" ]; then
        rm -rf "$staging"
        echo "skip $name (no tracked files)"
        return
    fi

    if [ ! -e "$dest" ]; then
        echo "install $name -> $dest ($agent)"
        [ "$CHECK_MODE" = 1 ] && DRIFT_FOUND=1
        if [ "$DRY_RUN" != 1 ] && ! mirror_tree "$staging" "$dest"; then
            echo "  FAILED to install $name at $dest" >&2
            rm -rf "$staging"
            return 1
        fi
        rm -rf "$staging"
        return
    fi

    local diff_out diff_status p
    local -a diff_excl=()
    for p in "${IGNORE_PATTERNS[@]}"; do diff_excl+=(-x "$p"); done
    if diff_out="$(diff -rq "${diff_excl[@]}" "$staging" "$dest" 2>&1)"; then
        diff_status=0
    else
        diff_status=$?
    fi
    if [ "$diff_status" -gt 1 ]; then
        echo "could not compare $name at $dest" >&2
        rm -rf "$staging"
        return 1
    fi
    if [ -z "$diff_out" ]; then
        echo "unchanged $name ($agent)"
        rm -rf "$staging"
        return
    fi

    echo
    echo "update $name -> $dest ($agent)"
    printf '%s\n' "$diff_out" | format_diff "$staging" "$dest"
    [ "$CHECK_MODE" = 1 ] && DRIFT_FOUND=1

    if [ "$DRY_RUN" = 1 ]; then
        echo "  (dry-run; not applying)"
        rm -rf "$staging"
        return
    fi

    if confirm "overwrite $dest?"; then
        if mirror_tree "$staging" "$dest"; then
            echo "  updated."
        else
            echo "  FAILED to update $name at $dest - it may be partially written." >&2
            rm -rf "$staging"
            return 1
        fi
    else
        echo "  skipped."
    fi
    rm -rf "$staging"
}

install_skill() {
    local name="$1" src="$2" destination agent dest_root
    for destination in "${DESTINATIONS[@]}"; do
        [ "$ABORT" = 1 ] && break
        agent="${destination%%|*}"
        dest_root="${destination#*|}"
        install_skill_to_destination "$name" "$src" "$agent" "$dest_root" || return 1
    done
}

add_discovered_skill() {
    local name="$1" src="$2"
    local existing
    for existing in "${SKILL_NAMES[@]+"${SKILL_NAMES[@]}"}"; do
        [ "$existing" = "$name" ] && return 0
    done
    SKILL_NAMES+=("$name")
    SKILL_PATHS+=("$src")
    if [ "$name" = "using-a-debugger" ]; then
        USING_A_DEBUGGER_SRC="$src"
    fi
}

discover_skills() {
    local top child
    SKILL_NAMES=()
    SKILL_PATHS=()
    USING_A_DEBUGGER_SRC=""
    for top in "$SRC_ROOT"/*/; do
        [ -d "$top" ] || continue
        if [ -f "$top/SKILL.md" ]; then
            add_discovered_skill "$(basename "$top")" "$top"
        else
            for child in "$top"/*/; do
                [ -d "$child" ] || continue
                if [ -f "$child/SKILL.md" ]; then
                    add_discovered_skill "$(basename "$child")" "$child"
                fi
            done
        fi
    done
}

found=0
discover_skills
for index in "${!SKILL_NAMES[@]}"; do
    [ "$ABORT" = 1 ] && break
    name="${SKILL_NAMES[$index]}"
    src="${SKILL_PATHS[$index]}"
    found=$((found + 1))
    is_selected "$name" || continue
    install_skill "$name" "$src" || APPLY_FAILED=1
done

if [ "$found" = 0 ]; then
    echo "warning: no installable skills found under $SRC_ROOT." >&2
    echo "         are you sure SKILL.md files are present under this tree?" >&2
    exit 1
fi

if [ "$ABORT" = 1 ]; then
    echo
    echo "aborted by user (q); remaining skills skipped."
fi

if [ "$CHECK_MODE" = 1 ] && [ "$DRIFT_FOUND" = 1 ]; then
    exit 1
fi

# Optional: install the debuggers using-a-debugger drives. Deps are machine-global
# (debuggers on PATH / known install roots), so this runs once from the source tree
# regardless of how many destinations were written. Opt-in via --setup-debuggers so
# a routine skill copy never triggers a system-package install.
if [ "$SETUP_DEBUGGERS" = 1 ] && [ "$CHECK_MODE" != 1 ] && [ "$ABORT" != 1 ] && [ "$APPLY_FAILED" != 1 ]; then
    setup_script="${USING_A_DEBUGGER_SRC:+$USING_A_DEBUGGER_SRC/scripts/setup-debuggers.py}"
    if ! is_selected using-a-debugger; then
        echo
        echo "--setup-debuggers: skipped (using-a-debugger not in the selected skills)"
    elif [ ! -f "$setup_script" ]; then
        echo
        echo "--setup-debuggers: skipped ($setup_script not found)" >&2
    else
        python_bin="$(command -v python3 || command -v python || true)"
        if [ -z "$python_bin" ]; then
            echo
            echo "--setup-debuggers: skipped (no python3/python on PATH)" >&2
        else
            echo
            echo "running debugger dependency setup ($setup_script)"
            setup_args=()
            [ "$DRY_RUN" = 1 ] && setup_args+=(--dry-run)
            "$python_bin" "$setup_script" "${setup_args[@]+"${setup_args[@]}"}" || true
        fi
    fi
fi

# Optional: hook management for skills declaring hooks (project-lock, progress-beacon,
# research-first, wrap). Opt-in via --hooks / --prune-hooks.
if [ "$HOOKS_MODE" = 1 ] || [ "$PRUNE_HOOKS" = 1 ]; then
    if [ "$ABORT" != 1 ] && [ "$APPLY_FAILED" != 1 ]; then
        python_bin="$(command -v python3 || command -v python || true)"
        manage_hooks_script="$REPO_DIR/scripts/manage_hooks.py"
        if [ ! -f "$manage_hooks_script" ]; then
            manage_hooks_script="$SRC_ROOT/scripts/manage_hooks.py"
        fi
        if [ -z "$python_bin" ]; then
            echo
            echo "--hooks: skipped (no python3/python on PATH)" >&2
        elif [ ! -f "$manage_hooks_script" ]; then
            echo
            echo "--hooks: skipped ($manage_hooks_script not found)" >&2
        else
            echo
            hook_args=()
            [ "$ASSUME_YES" = 1 ] && hook_args+=(-y)
            [ "$DRY_RUN" = 1 ] && hook_args+=(-n)
            [ "$CHECK_MODE" = 1 ] && hook_args+=(--check)
            [ "$PRUNE_HOOKS" = 1 ] && hook_args+=(--prune)

            for destination in "${DESTINATIONS[@]}"; do
                agent="${destination%%|*}"
                case "$agent" in
                    claude) hook_args+=(--claude) ;;
                    gemini) hook_args+=(--gemini) ;;
                    hermes) hook_args+=(--hermes) ;;
                    agents) hook_args+=(--agents) ;;
                esac
            done

            for sel in "${SELECTED[@]+"${SELECTED[@]}"}"; do
                hook_args+=("$sel")
            done

            if ! "$python_bin" "$manage_hooks_script" "${hook_args[@]+"${hook_args[@]}"}"; then
                if [ "$CHECK_MODE" = 1 ]; then
                    DRIFT_FOUND=1
                else
                    APPLY_FAILED=1
                fi
            fi
        fi
    fi
fi

if [ "$APPLY_FAILED" = 1 ]; then
    echo
    echo "one or more skills failed to install; see the errors above." >&2
    exit 1
fi

if [ "$CHECK_MODE" = 1 ] && [ "$DRIFT_FOUND" = 1 ]; then
    exit 1
fi
