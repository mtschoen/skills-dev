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
