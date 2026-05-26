# Installer Allowlist Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the installer's failing exclude-list with a git-native top-level allowlist so generated junk (`__pycache__` etc.) can never ship, and make every install a true mirror that purges cruft left by prior installs.

**Architecture:** For each skill, derive the file set from `git -C <skill> ls-files` (tracked files only — untracked junk is structurally excluded), filter to a top-level allowlist (`SKILL.md` + `scripts/` + `references/` + `assets/` plus extras from an optional `.skillpack` manifest), copy the surviving tracked paths from the working tree into a temp staging dir (so uncommitted edits still install), then mirror staging → destination (removing dest entries absent from staging). Keep dual bash + batch — no Python, since git is already a hard dependency (skills are submodules). `cost-estimator/scripts/` is restructured to runtime-only so the allowlist needs no within-directory pruning.

**Tech Stack:** Bash + Windows batch; `git ls-files`; `cp`/`diff`/`mktemp` (bash) and `robocopy /MIR`/`copy` (batch); pytest (cost-estimator).

---

## Phase 2: `install-skills.sh` allowlist rewrite (TDD)

### Task 3: Write the integration test harness

A self-contained bash harness that builds a synthetic skill fixture (a real git repo with tracked + untracked files), runs the installer into a throwaway dest, and asserts the allowlist + cleanup + working-tree behavior. It also drives the `.bat` on Windows via `cmd.exe` (used in Phase 3). Written first so it FAILS against the current installer.

**Files:**
- Create: `tests/test-install.sh`

`tests/` is a new top-level dir in the umbrella repo. The installer's main loop only processes dirs containing `.git`, so a plain `tests/` dir is never treated as a skill.

- [x] **Step 1: Write `tests/test-install.sh`**

```bash
#!/usr/bin/env bash
# Integration test for install-skills.{sh,bat}.
# Builds a synthetic skill (git repo with tracked + untracked files), installs
# it into a throwaway dest, and asserts the top-level allowlist + cleanup +
# working-tree behavior. On Windows (cmd.exe present) also exercises the .bat.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/skilltest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; FAILED=1; }
assert_exists()    { [ -e "$2" ] && pass "$1" || fail "$1 (missing: $2)"; }
assert_absent()    { [ ! -e "$2" ] && pass "$1" || fail "$1 (present: $2)"; }
assert_contains()  { grep -q "$3" "$2" 2>/dev/null && pass "$1" || fail "$1"; }

# --- build the synthetic skill fixture ------------------------------------
build_fixture() {
    local src="$WORK/src"
    rm -rf "$src"; mkdir -p "$src/demoskill"
    local s="$src/demoskill"
    mkdir -p "$s/scripts/__pycache__" "$s/references" "$s/tests" "$s/hooks"
    printf '%s\n' "---" "name: demoskill" "description: demo" "---" "body" > "$s/SKILL.md"
    echo "print('run')"            > "$s/scripts/run.py"
    echo "cached"                  > "$s/scripts/__pycache__/run.cpython-313.pyc"
    echo "ref"                     > "$s/references/guide.md"
    echo "devtest"                 > "$s/tests/test_demo.py"
    echo "readme"                  > "$s/README.md"
    echo "hookbody"                > "$s/hooks/h.sh"
    # gitignore the cache so it is untracked, like the real skills
    printf '%s\n' "__pycache__/" "*.pyc" > "$s/.gitignore"
    ( cd "$s" && git init -q && git add SKILL.md scripts/run.py references/guide.md \
        tests/test_demo.py README.md hooks/h.sh .gitignore && \
        git -c user.email=t@t -c user.name=t commit -qm init )
    echo "$src"
}

# --- run the installer + assert the shipped surface -----------------------
# args: <label> <dest-skills-dir>
assert_install() {
    local label="$1" skills="$2"
    echo "[$label] baseline allowlist + junk exclusion"
    assert_exists "$label: SKILL.md shipped"        "$skills/demoskill/SKILL.md"
    assert_exists "$label: scripts/run.py shipped"  "$skills/demoskill/scripts/run.py"
    assert_exists "$label: references/ shipped"     "$skills/demoskill/references/guide.md"
    assert_absent "$label: __pycache__ NOT shipped" "$skills/demoskill/scripts/__pycache__"
    assert_absent "$label: tests/ NOT shipped"      "$skills/demoskill/tests"
    assert_absent "$label: README.md NOT shipped"   "$skills/demoskill/README.md"
    assert_absent "$label: hooks/ NOT shipped (no manifest)" "$skills/demoskill/hooks"
}

# ===== .sh under test =====
SRC="$(build_fixture)"
HOME_SH="$WORK/home_sh"; mkdir -p "$HOME_SH"
HOME="$HOME_SH" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_install ".sh" "$HOME_SH/.claude/skills"

echo "[.sh] cleanup of prior-install cruft"
mkdir -p "$HOME_SH/.claude/skills/demoskill/reports" \
         "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__"
echo stale > "$HOME_SH/.claude/skills/demoskill/reports/old.txt"
echo stale > "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__/x.pyc"
HOME="$HOME_SH" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_absent ".sh: stale reports/ purged"  "$HOME_SH/.claude/skills/demoskill/reports"
assert_absent ".sh: stale __pycache__ purged" "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__"

echo "[.sh] manifest include (hooks/)"
printf '%s\n' "hooks/" > "$SRC/demoskill/.skillpack"
( cd "$SRC/demoskill" && git add .skillpack && git -c user.email=t@t -c user.name=t commit -qm skillpack )
HOME="$HOME_SH" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_exists ".sh: hooks/ shipped via manifest" "$HOME_SH/.claude/skills/demoskill/hooks/h.sh"
assert_absent ".sh: .skillpack NOT shipped"       "$HOME_SH/.claude/skills/demoskill/.skillpack"

echo "[.sh] uncommitted working-tree edit installs"
printf '%s\n' "EDITED-MARKER" >> "$SRC/demoskill/SKILL.md"   # not committed
HOME="$HOME_SH" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_contains ".sh: uncommitted edit propagated" "$HOME_SH/.claude/skills/demoskill/SKILL.md" "EDITED-MARKER"

# ===== .bat under test (Windows only) =====
if command -v cmd.exe >/dev/null 2>&1; then
    SRC2="$(build_fixture)"
    HOME_BAT="$WORK/home_bat"; mkdir -p "$HOME_BAT"
    SRC2_WIN="$(cygpath -w "$SRC2")"; HOME_BAT_WIN="$(cygpath -w "$HOME_BAT")"
    USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude demoskill >/dev/null
    assert_install ".bat" "$HOME_BAT/.claude/skills"

    echo "[.bat] cleanup of prior-install cruft"
    mkdir -p "$HOME_BAT/.claude/skills/demoskill/reports"
    echo stale > "$HOME_BAT/.claude/skills/demoskill/reports/old.txt"
    USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude demoskill >/dev/null
    assert_absent ".bat: stale reports/ purged" "$HOME_BAT/.claude/skills/demoskill/reports"
else
    echo "[.bat] skipped (no cmd.exe on this platform)"
fi

echo
if [ "$FAILED" = 0 ]; then echo "ALL TESTS PASSED"; else echo "TESTS FAILED"; fi
exit "$FAILED"
```

- [x] **Step 2: Run the harness against the CURRENT installer to confirm it FAILS**

Run:
```bash
bash tests/test-install.sh
```
Expected: `TESTS FAILED`. The current installer has no `SKILLS_SRC_ROOT` seam, so it scans the real skills-dir instead of the fixture, never installs `demoskill`, and the `assert_exists` checks fail on missing files. That RED confirms the harness runs and gates the rewrite. (Once Task 4 adds the seam and allowlist, the `__pycache__`-exclusion and cleanup assertions become the meaningful ones.)

- [x] **Step 3: Commit the test harness**

```bash
git add tests/test-install.sh
git commit -m "test: integration harness for installer allowlist + cleanup

Builds a synthetic skill fixture (tracked + untracked files) and asserts
the top-level allowlist, junk exclusion, prior-install cleanup, manifest
includes, and working-tree-edit behavior. Drives .bat on Windows too.
Currently RED against the exclude-list installer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4: Rewrite `install-skills.sh` with the allowlist + staging-mirror

**Files:**
- Modify (full rewrite): `install-skills.sh`

- [x] **Step 1: Replace the entire contents of `install-skills.sh`**

```bash
#!/usr/bin/env bash
# Install skills from this repo into one or more agent config dirs.
#
# Each top-level dir here is a skill submodule with a SKILL.md at its root.
# The installer ships only GIT-TRACKED files (via `git ls-files`), filtered to
# a top-level allowlist: SKILL.md + scripts/ + references/ + assets/, plus any
# extra top-level entries listed in the skill's optional `.skillpack` manifest.
# Shipping tracked files only means generated junk (e.g. __pycache__) can never
# leak. Each install is a true mirror of a clean staging tree, so files left in
# the destination by older installs are removed.
#
# Usage: ./install-skills.sh [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
#   -y / --yes       overwrite without prompting
#   -n / --dry-run   show what would change, don't copy
#   --agents         install to ~/.agents/skills (canonical source of truth)
#   --claude         install to ~/.claude/skills (Claude's mirror of ~/.agents/skills)
#   --gemini         install to ~/.gemini/skills (Antigravity's global skills dir)
#   --all            install to all known agent skill dirs
#   positional args  limit to specific skill names (default: all)
#
# With no agent flag, installs to ~/.agents/skills plus the two harnesses that
# can't read it directly: ~/.claude/skills (Claude) and ~/.gemini/skills
# (Antigravity). Codex reads ~/.agents/skills natively, so it needs no copy.
#
# Test seam: set SKILLS_SRC_ROOT to override the source dir scanned for skills.

set -euo pipefail

SRC_ROOT="${SKILLS_SRC_ROOT:-"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"}"

ASSUME_YES=0
DRY_RUN=0
SELECTED=()
DESTINATIONS=()

# Baseline top-level entries shipped for every skill (Agent Skills convention
# + the required SKILL.md). Extra entries come from each skill's .skillpack.
BASELINE_INCLUDES=(SKILL.md scripts references assets)

add_destination() {
    local name="$1" path="$2"
    local existing
    for existing in "${DESTINATIONS[@]+"${DESTINATIONS[@]}"}"; do
        [ "$existing" = "$name|$path" ] && return 0
    done
    DESTINATIONS+=("$name|$path")
}

add_all_destinations() {
    add_destination agents "${HOME}/.agents/skills"
    add_destination claude "${HOME}/.claude/skills"
    add_destination gemini "${HOME}/.gemini/skills"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes) ASSUME_YES=1; shift ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        --agents) add_destination agents "${HOME}/.agents/skills"; shift ;;
        --claude) add_destination claude "${HOME}/.claude/skills"; shift ;;
        --gemini) add_destination gemini "${HOME}/.gemini/skills"; shift ;;
        --all) add_all_destinations; shift ;;
        -h|--help)
            sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) echo "unknown flag: $1" >&2; exit 2 ;;
        *) SELECTED+=("$1"); shift ;;
    esac
done

if [ "${#DESTINATIONS[@]}" -eq 0 ]; then
    add_all_destinations
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
        read -r -p "$prompt [y/N] " reply </dev/tty
    elif [ -t 0 ]; then
        read -r -p "$prompt [y/N] " reply
    else
        echo "  (no tty; skipping. re-run with -y to overwrite.)" >&2
        return 1
    fi
    [[ "$reply" =~ ^[Yy]$ ]]
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
            mkdir -p "$dest"
            cp -a "$staging/." "$dest/"
        fi
        rm -rf "$staging"
        return
    fi

    local diff_out
    diff_out="$(diff -rq "$staging" "$dest" 2>&1 || true)"
    if [ -z "$diff_out" ]; then
        echo "unchanged $name ($agent)"
        rm -rf "$staging"
        return
    fi

    echo
    echo "update $name -> $dest ($agent; 'Only in (shipped)'=add, 'Only in (installed)'=remove):"
    printf '%s\n' "$diff_out" \
        | sed -e "s#$staging#(shipped)#g" -e "s#$dest#(installed)#g" -e 's/^/  /'

    if [ "$DRY_RUN" = 1 ]; then
        echo "  (dry-run; not applying)"
        rm -rf "$staging"
        return
    fi

    if confirm "overwrite $dest?"; then
        rm -rf "$dest"
        mkdir -p "$dest"
        cp -a "$staging/." "$dest/"
        echo "  updated."
    else
        echo "  skipped."
    fi
    rm -rf "$staging"
}

install_skill() {
    local name="$1" destination agent dest_root
    for destination in "${DESTINATIONS[@]}"; do
        agent="${destination%%|*}"
        dest_root="${destination#*|}"
        install_skill_to_destination "$name" "$agent" "$dest_root"
    done
}

for src in "$SRC_ROOT"/*/; do
    name="$(basename "$src")"
    [ -e "$src/.git" ] || continue       # only git submodules / repos
    is_selected "$name" || continue
    install_skill "$name"
done
```

- [x] **Step 2: Run the harness — `.sh` assertions must now pass**

Run:
```bash
bash tests/test-install.sh
```
Expected: every `[.sh]` line prints `PASS`. (The `[.bat]` block still fails until Phase 3 — overall result will be `TESTS FAILED` because of `.bat`. Confirm all `.sh` lines are PASS before continuing.)

- [x] **Step 3: Commit the bash rewrite**

```bash
git add install-skills.sh
git commit -m "feat: install-skills.sh ships git-tracked allowlist, mirrors dest

Replace exclude-list + working-tree copy with: git ls-files -> top-level
allowlist (SKILL.md/scripts/references/assets + .skillpack extras) ->
clean staging tree -> mirror into dest. Untracked junk (__pycache__) can
no longer ship; stale files from prior installs are purged. SKILLS_SRC_ROOT
test seam added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3: `install-skills.bat` parity

### Task 5: Rewrite `install-skills.bat` with the allowlist + staging-mirror

Mirror the bash logic: build a clean staging tree from `git ls-files` filtered to the top-level allowlist, then `robocopy /MIR` staging → dest (no `/XD`, so the dest-pinning bug is gone).

**Files:**
- Modify (full rewrite): `install-skills.bat`

- [ ] **Step 1: Replace the entire contents of `install-skills.bat`**

```bat
@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into one or more agent config dirs.
rem
rem Each top-level dir here is a skill submodule with a SKILL.md at its root.
rem The installer ships only GIT-TRACKED files (git ls-files), filtered to a
rem top-level allowlist: SKILL.md + scripts\ + references\ + assets\, plus any
rem extra top-level entries listed in the skill's optional .skillpack manifest.
rem Tracked-only shipping means generated junk (e.g. __pycache__) can't leak.
rem Each install mirrors a clean staging tree, so files left by older installs
rem are removed.
rem
rem Usage: install-skills.bat [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
rem   -y / --yes       overwrite without prompting
rem   -n / --dry-run   show what would change, don't copy
rem   --agents         install to %%USERPROFILE%%\.agents\skills
rem   --claude         install to %%USERPROFILE%%\.claude\skills
rem   --gemini         install to %%USERPROFILE%%\.gemini\skills
rem   --all            install to all known agent skill dirs
rem   positional args  limit to specific skill names (default: all)
rem
rem Test seam: set SKILLS_SRC_ROOT to override the source dir scanned.

set "SRC_ROOT=%~dp0"
if "%SRC_ROOT:~-1%"=="\" set "SRC_ROOT=%SRC_ROOT:~0,-1%"
if defined SKILLS_SRC_ROOT set "SRC_ROOT=%SKILLS_SRC_ROOT%"

set "ASSUME_YES=0"
set "DRY_RUN=0"
set "SELECTED="
set "DEST_COUNT=0"

:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="-y"         (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="--yes"      (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="-n"         (set "DRY_RUN=1"    & shift & goto parse_args)
if /i "%~1"=="--dry-run"  (set "DRY_RUN=1"    & shift & goto parse_args)
if /i "%~1"=="--agents"   (call :add_dest agents "%USERPROFILE%\.agents\skills" & shift & goto parse_args)
if /i "%~1"=="--claude"   (call :add_dest claude "%USERPROFILE%\.claude\skills" & shift & goto parse_args)
if /i "%~1"=="--gemini"   (call :add_dest gemini "%USERPROFILE%\.gemini\skills" & shift & goto parse_args)
if /i "%~1"=="--all"      (call :add_all_dests & shift & goto parse_args)
if /i "%~1"=="-h"         goto usage
if /i "%~1"=="--help"     goto usage
set "arg=%~1"
if "!arg:~0,1!"=="-" (
    echo unknown flag: %~1 1>&2
    exit /b 2
)
set "SELECTED=!SELECTED! !arg!"
shift
goto parse_args

:parse_done
if "%DEST_COUNT%"=="0" call :add_all_dests

set "BASELINE= SKILL.md scripts references assets "

for /d %%D in ("%SRC_ROOT%\*") do (
    set "name=%%~nxD"
    set "src=%%~fD"
    if exist "!src!\.git" call :maybe_install "!name!" "!src!"
)

endlocal
exit /b 0

:add_dest
for /l %%I in (1,1,%DEST_COUNT%) do (
    if /i "!DEST_%%I_NAME!"=="%~1" if /i "!DEST_%%I_PATH!"=="%~2" exit /b 0
)
set /a DEST_COUNT+=1
set "DEST_%DEST_COUNT%_NAME=%~1"
set "DEST_%DEST_COUNT%_PATH=%~2"
exit /b 0

:add_all_dests
call :add_dest agents "%USERPROFILE%\.agents\skills"
call :add_dest claude "%USERPROFILE%\.claude\skills"
call :add_dest gemini "%USERPROFILE%\.gemini\skills"
exit /b 0

:maybe_install
call :is_selected "%~1"
if errorlevel 1 exit /b 0
for /l %%I in (1,1,%DEST_COUNT%) do (
    call :install_skill "%~1" "%~2" "!DEST_%%I_NAME!" "!DEST_%%I_PATH!"
)
exit /b 0

:is_selected
if "!SELECTED!"=="" exit /b 0
for %%S in (!SELECTED!) do (
    if /i "%%~S"=="%~1" exit /b 0
)
exit /b 1

:install_skill
set "n=%~1"
set "src=%~2"
set "agent=%~3"
set "dest_root=%~4"

if not exist "!src!\SKILL.md" (
    echo skip !n! ^(no SKILL.md^)
    exit /b 0
)

set "dest=!dest_root!\!n!"
set "staging=%TEMP%\skillinst-!agent!-!n!-%RANDOM%%RANDOM%"
if exist "!staging!" rmdir /s /q "!staging!"
mkdir "!staging!"
call :build_staging "!src!" "!staging!"

if not exist "!dest!" (
    echo install !n! -^> !dest! ^(!agent!^)
    if "!DRY_RUN!"=="1" ( rmdir /s /q "!staging!" & exit /b 0 )
    if not exist "!dest_root!" mkdir "!dest_root!"
    robocopy "!staging!" "!dest!" /MIR /NJH /NJS /NDL /NP /NS /NC /NFL >nul
    rmdir /s /q "!staging!"
    exit /b 0
)

set "tmpout=%TEMP%\install-skills-!agent!-!n!.txt"
robocopy "!staging!" "!dest!" /MIR /L /NJH /NJS /NDL /NP /NS /NC /FP > "!tmpout!"
set "rc=!errorlevel!"

if !rc! geq 8 (
    echo robocopy /L failed for !n! ^(!agent!, exit !rc!^) 1>&2
    del "!tmpout!" 2>nul
    rmdir /s /q "!staging!"
    exit /b 0
)

if !rc! equ 0 (
    echo unchanged !n! ^(!agent!^)
    del "!tmpout!" 2>nul
    rmdir /s /q "!staging!"
    exit /b 0
)

echo.
echo update !n! -^> !dest! ^(!agent!, changes below; *EXTRA = removed^):
for /f "usebackq delims=" %%L in ("!tmpout!") do echo   %%L
del "!tmpout!" 2>nul

if "!DRY_RUN!"=="1" (
    echo   ^(dry-run; not applying^)
    rmdir /s /q "!staging!"
    exit /b 0
)

call :confirm "overwrite !dest!?"
if errorlevel 1 (
    echo   skipped.
    rmdir /s /q "!staging!"
    exit /b 0
)
if not exist "!dest_root!" mkdir "!dest_root!"
robocopy "!staging!" "!dest!" /MIR /NJH /NJS /NDL /NP /NS /NC /NFL >nul
echo   updated.
rmdir /s /q "!staging!"
exit /b 0

:build_staging
set "bs_src=%~1"
set "bs_staging=%~2"
rem include set = baseline + .skillpack extras (space-delimited, trimmed)
set "INCLSET=%BASELINE%"
if exist "!bs_src!\.skillpack" (
    for /f "usebackq eol=# tokens=* delims=" %%E in ("!bs_src!\.skillpack") do (
        set "e=%%E"
        set "e=!e: =!"
        if "!e:~-1!"=="/" set "e=!e:~0,-1!"
        if not "!e!"=="" set "INCLSET=!INCLSET!!e! "
    )
)
rem copy each tracked file whose top-level component is in the include set
for /f "usebackq delims=" %%F in (`git -C "!bs_src!" ls-files`) do (
    set "rel=%%F"
    for /f "tokens=1 delims=/" %%T in ("%%F") do set "top=%%T"
    set "hit="
    for %%I in (!INCLSET!) do if /i "%%I"=="!top!" set "hit=1"
    if defined hit (
        set "relwin=!rel:/=\!"
        if exist "!bs_src!\!relwin!" (
            for %%P in ("!bs_staging!\!relwin!") do if not exist "%%~dpP" mkdir "%%~dpP"
            copy /y "!bs_src!\!relwin!" "!bs_staging!\!relwin!" >nul
        )
    )
)
exit /b 0

:confirm
if "!ASSUME_YES!"=="1" exit /b 0
set "reply=__NOPROMPT__"
set /p "reply=%~1 [y/N] "
if "!reply!"=="__NOPROMPT__" (
    echo   ^(no tty; skipping. re-run with -y to overwrite.^) 1>&2
    exit /b 1
)
if /i "!reply!"=="y" exit /b 0
exit /b 1

:usage
echo Install skills from this repo into one or more agent config dirs.
echo.
echo Usage: install-skills.bat [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
echo   -y / --yes       overwrite without prompting
echo   -n / --dry-run   show what would change, don't copy
echo   --agents         install to %%USERPROFILE%%\.agents\skills
echo   --claude         install to %%USERPROFILE%%\.claude\skills
echo   --gemini         install to %%USERPROFILE%%\.gemini\skills
echo   --all            install to all known agent skill dirs
echo   positional args  limit to specific skill names ^(default: all^)
exit /b 0
```

- [ ] **Step 2: Convert the file to CRLF line endings**

The Write tool emits LF on Windows, which breaks batch `:label` lookup. Run:
```bash
sed -i 's/\r$//; s/$/\r/' install-skills.bat
```
(Strips any existing CR first to avoid doubling, then appends CR to every line.)

- [ ] **Step 3: Run the harness — both `.sh` and `.bat` must pass**

Run:
```bash
bash tests/test-install.sh
```
Expected: final line `ALL TESTS PASSED`, exit 0. Every `[.sh]` and `[.bat]` assertion prints `PASS`.

- [ ] **Step 4: Commit the batch rewrite**

```bash
git add install-skills.bat
git commit -m "feat: install-skills.bat ships git-tracked allowlist, mirrors dest

Batch parity with the .sh rewrite: git ls-files -> top-level allowlist
-> clean staging tree -> robocopy /MIR (no /XD, so stale dest dirs are
purged instead of pinned). Integration harness now green on both shells.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4: Docs + umbrella integration

### Task 6: Update `CLAUDE.md` to describe the allowlist + `.skillpack`

**Files:**
- Modify: `CLAUDE.md` (the "Layout" section; add a `.skillpack` note)

- [ ] **Step 1: Replace the "Layout" section body**

Find the paragraph in `CLAUDE.md` under `## Layout` that begins "Per-skill repos use the **root layout**" and currently describes the installer as "excluding dev-only files (`evals/`, `tests/`, ...)". Replace that installer description with:

```markdown
The installer (`install-skills.{sh,bat}`) ships only **git-tracked** files
(`git ls-files`), filtered to a **top-level allowlist**: `SKILL.md` +
`scripts/` + `references/` + `assets/`, plus any extra top-level entries a
skill declares in an optional `.skillpack` manifest at its repo root (one
entry per line, `#` comments). Shipping tracked-only means generated junk
(`__pycache__`, `.pytest_cache`) can never leak; the allowlist means dev dirs
(`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`) are excluded by
omission. Each install mirrors a clean staging tree into the destination, so
files left by older installs are removed. Skill validation is delegated to the
official Agent Skills validator: CI runs `agentskills validate` (pinned
`skills-ref==0.1.1`) over every `.gitmodules` skill via
`scripts/validate_skills.py`, which keeps the fleet-level anti-vacuous / WIP-skip
guards; markdownlint covers skill prose.
```

- [ ] **Step 2: Add a `.skillpack` bullet under "Naming conventions"**

Append to the "Naming conventions" list:
```markdown
- A skill ships extra top-level content (beyond `SKILL.md` + `scripts/` +
  `references/` + `assets/`) by listing it in a `.skillpack` file at the skill's
  repo root. Current users: `progress-beacon` (`hooks/`), `cost-estimator`
  (`REPORT_TEMPLATE.md`). The `.skillpack` file is itself never installed.
```

- [ ] **Step 3: Commit the docs update**

```bash
git add CLAUDE.md
git commit -m "docs: describe installer allowlist + .skillpack manifest

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7: Full-fleet dry-run, submodule-pointer bumps, cleanup verification

**Files:**
- Modify: umbrella submodule pointers for `cost-estimator`, `progress-beacon`

- [ ] **Step 1: Dry-run the real fleet on both installers and eyeball removals**

Run:
```bash
bash install-skills.sh -n --claude
```
Expected: for `cost-estimator`, the change list shows the leaked cruft as removals — `Only in (installed)` lines for `scripts/__pycache__`, `.pytest_cache`, `reports`, `screenshot*.png`, and the relocated dev scripts. For most skills: `unchanged`.

Then on Windows:
```bash
cmd.exe /c install-skills.bat -n --claude
```
Expected: the same cruft appears as `*EXTRA` (robocopy's removal marker) for `cost-estimator`.

- [ ] **Step 2: Apply the real install and confirm the cruft is gone**

Run:
```bash
bash install-skills.sh -y --claude cost-estimator
ls -a ~/.claude/skills/cost-estimator ~/.claude/skills/cost-estimator/scripts
```
Expected: no `__pycache__`, `.pytest_cache`, `reports/`, `screenshot*.png`, no `tests/`, no `README.md`, no `.skillpack`; `REPORT_TEMPLATE.md` and `scripts/*.py` (runtime only) present.

Verify a manifest skill:
```bash
bash install-skills.sh -y --claude progress-beacon
ls ~/.claude/skills/progress-beacon/hooks
```
Expected: `hooks/` present with `prompt-reminder.sh` and `recency-nudge.sh`.

- [ ] **Step 3: Stage the submodule-pointer bumps in the umbrella**

The Phase 1–2 submodule commits moved the recorded HEADs. Stage the pointers:
```bash
git add cost-estimator progress-beacon
git status --short    # expect: M cost-estimator, M progress-beacon
```

- [ ] **Step 4: Commit the umbrella submodule-pointer bumps**

```bash
git commit -m "chore: bump cost-estimator + progress-beacon (scripts/ restructure, .skillpack)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Final full harness run**

```bash
bash tests/test-install.sh
```
Expected: `ALL TESTS PASSED`. This is the verification gate before declaring the branch done.

**Pushing** (`scripts/push-all.{sh,bat}`) and branch integration are deferred to branch-finish (superpowers:finishing-a-development-branch), per the repo convention of pushing only when asked.
