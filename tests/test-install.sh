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
assert_exists()    { if [ -e "$2" ];   then pass "$1"; else fail "$1 (missing: $2)"; fi; }
assert_absent()    { if [ ! -e "$2" ]; then pass "$1"; else fail "$1 (present: $2)"; fi; }
assert_contains()  { if grep -q "$3" "$2" 2>/dev/null; then pass "$1"; else fail "$1"; fi; }
assert_tree_matches() {
    if diff -r -q "$2" "$3" >/dev/null; then
        pass "$1"
    else
        fail "$1 (added, deleted, or byte-changed files below $3)"
    fi
}

# Git Bash/MSYS hands POSIX paths to native Windows programs, which cannot read
# them; cygpath converts. Elsewhere the path is already native.
native_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s\n' "$1"; fi
}

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

add_debugger_fixture() {
    local src="$1"
    local s="$src/using-a-debugger"
    mkdir -p "$s/scripts"
    printf '%s\n' "---" "name: using-a-debugger" "description: debug" "---" "body" > "$s/SKILL.md"
    cat > "$s/scripts/setup-debuggers.py" <<'PY'
import os
from pathlib import Path

Path(os.environ["DEBUGGER_MARKER"]).write_text("ran", encoding="utf-8")
PY
    ( cd "$s" && git init -q && git add SKILL.md scripts/setup-debuggers.py && \
        git -c user.email=t@t -c user.name=t commit -qm init )
}

add_hook_skill_fixture() {
    local src="$1"
    local s="$src/project-lock"
    mkdir -p "$s/hooks"
    printf '%s\n' "---" "name: project-lock" "description: lock" "---" "body" > "$s/SKILL.md"
    printf '%s\n' "hooks/" > "$s/.skillpack"
    printf '%s\n' "#!/usr/bin/env python3" "print('lock')" > "$s/hooks/pre_tool_use.py"
    ( cd "$s" && git init -q && git add SKILL.md .skillpack hooks/pre_tool_use.py && \
        git -c user.email=t@t -c user.name=t commit -qm init )
}

# --- run the installer + assert the shipped surface -----------------------

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
# The installer resolves the harness home twice, and the two halves disagree on
# Windows: install-skills.sh reads $HOME, while the hook step it shells out to
# (scripts/manage_hooks.py) resolves Path.home(), which reads USERPROFILE and
# ignores HOME. Sandboxing only HOME therefore leaves the hook step pointed at
# the developer's real ~/.claude, where it both asserts against the wrong file
# and writes hook registrations. Set both; USERPROFILE is inert on POSIX.
HOME_SH_NATIVE="$(native_path "$HOME_SH")"
HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_install ".sh" "$HOME_SH/.claude/skills"

echo "[.sh] cleanup of prior-install cruft"
mkdir -p "$HOME_SH/.claude/skills/demoskill/reports" \
         "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__"
echo stale > "$HOME_SH/.claude/skills/demoskill/reports/old.txt"
echo stale > "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__/x.pyc"
HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_absent ".sh: stale reports/ purged"  "$HOME_SH/.claude/skills/demoskill/reports"
assert_exists ".sh: stale __pycache__ preserved" "$HOME_SH/.claude/skills/demoskill/scripts/__pycache__/x.pyc"

echo "[.sh] manifest include (hooks/)"
printf '%s\n' "hooks/" > "$SRC/demoskill/.skillpack"
( cd "$SRC/demoskill" && git add .skillpack && git -c user.email=t@t -c user.name=t commit -qm skillpack )
HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_exists ".sh: hooks/ shipped via manifest" "$HOME_SH/.claude/skills/demoskill/hooks/h.sh"
assert_absent ".sh: .skillpack NOT shipped"       "$HOME_SH/.claude/skills/demoskill/.skillpack"

echo "[.sh] uncommitted working-tree edit installs"
printf '%s\n' "EDITED-MARKER" >> "$SRC/demoskill/SKILL.md"   # not committed
HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill >/dev/null
assert_contains ".sh: uncommitted edit propagated" "$HOME_SH/.claude/skills/demoskill/SKILL.md" "EDITED-MARKER"

echo "[.sh] a failed apply is reported and exits nonzero"
# A stub rsync that always fails is the injection: it needs no privileges and
# behaves identically everywhere. Making the destination read-only does NOT
# work -- `rsync -a` re-chmods the destination from the source's modes and
# succeeds anyway, so that version of this test passed while proving nothing.
stub_bin="$WORK/stubbin"; mkdir -p "$stub_bin"
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "$stub_bin/rsync"
chmod +x "$stub_bin/rsync"
printf '%s\n' "FAILURE-PATH-MARKER" >> "$SRC/demoskill/SKILL.md"
fail_out="$(PATH="$stub_bin:$PATH" HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" \
    SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude demoskill 2>&1)"
fail_rc=$?
if [ "$fail_rc" -ne 0 ]; then pass ".sh: failed apply exits nonzero"; else fail ".sh: failed apply exit $fail_rc"; fi
case "$fail_out" in
    *"updated."*) fail ".sh: failed apply still claimed 'updated.'" ;;
    *)            pass ".sh: failed apply does not claim 'updated.'" ;;
esac
case "$fail_out" in
    *FAILED*) pass ".sh: failed apply names the destination it could not write" ;;
    *)        fail ".sh: failed apply printed no FAILED line" ;;
esac

echo "[.sh] hook registration with --hooks"
add_hook_skill_fixture "$SRC"
HOME="$HOME_SH" USERPROFILE="$HOME_SH_NATIVE" SKILLS_SRC_ROOT="$SRC" bash "$REPO_ROOT/install-skills.sh" -y --claude --hooks project-lock >/dev/null
assert_exists ".sh: project-lock hook shipped" "$HOME_SH/.claude/skills/project-lock/hooks/pre_tool_use.py"
assert_exists ".sh: claude settings.json created" "$HOME_SH/.claude/settings.json"
assert_contains ".sh: pre_tool_use registered in settings.json" "$HOME_SH/.claude/settings.json" "pre_tool_use.py"
assert_exists ".sh: hook decisions file created" "$HOME_SH/.claude/skills/.hook-decisions.json"
assert_contains ".sh: hook decision recorded" "$HOME_SH/.claude/skills/.hook-decisions.json" "project-lock/pre_tool_use"

# ===== .bat under test (Windows only) =====
if command -v cmd.exe >/dev/null 2>&1; then
    # MSYS_NO_PATHCONV=1: stop Git Bash from rewriting cmd.exe's "/c" switch
    # into "C:/" (which silently drops to an interactive shell, running nothing).
    SRC2="$(build_fixture)"
    HOME_BAT="$WORK/home_bat"; mkdir -p "$HOME_BAT"
    SRC2_WIN="$(cygpath -w "$SRC2")"; HOME_BAT_WIN="$(cygpath -w "$HOME_BAT")"
    USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude demoskill >/dev/null
    assert_install ".bat" "$HOME_BAT/.claude/skills"

    echo "[.bat] content-identical check ignores metadata drift"
    touch -t 203001010101 "$SRC2/demoskill/SKILL.md"
    bat_metadata_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" --check --claude demoskill 2>&1)"
    bat_metadata_rc=$?
    if [ "$bat_metadata_rc" -eq 0 ]; then pass ".bat: metadata-only check exits 0"; else fail ".bat: metadata-only check exit $bat_metadata_rc"; fi
    case "$bat_metadata_out" in
        *"unchanged demoskill (claude)"*) pass ".bat: metadata-only drift reports unchanged" ;;
        *) fail ".bat: metadata-only drift did not report unchanged" ;;
    esac
    case "$bat_metadata_out" in
        *"update demoskill"*) fail ".bat: metadata-only drift reported an update" ;;
        *) pass ".bat: metadata-only drift reports no update" ;;
    esac

    echo "[.bat] dry run catches equal-size content drift with matched mtime"
    bat_equal_source="$SRC2/demoskill/references/guide.md"
    bat_equal_dest="$HOME_BAT/.claude/skills/demoskill/references/guide.md"
    printf '%s\n' "alt" > "$bat_equal_dest"
    touch -r "$bat_equal_source" "$bat_equal_dest"
    bat_equal_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -n --claude demoskill 2>&1)"
    bat_equal_rc=$?
    if [ "$bat_equal_rc" -eq 0 ]; then pass ".bat: equal-metadata dry run exits 0"; else fail ".bat: equal-metadata dry run exit $bat_equal_rc"; fi
    case "$bat_equal_out" in
        *"update demoskill"*) pass ".bat: equal-metadata content drift reports an update" ;;
        *) fail ".bat: equal-metadata content drift did not report an update" ;;
    esac
    case "$bat_equal_out" in
        *"~ references\\guide.md (changed)"*) pass ".bat: equal-metadata content drift appears in preview" ;;
        *) fail ".bat: equal-metadata content drift missing from preview" ;;
    esac
    bat_equal_apply_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude demoskill 2>&1)"
    bat_equal_apply_rc=$?
    if [ "$bat_equal_apply_rc" -eq 0 ]; then pass ".bat: equal-metadata apply exits 0"; else fail ".bat: equal-metadata apply exit $bat_equal_apply_rc"; fi
    case "$bat_equal_apply_out" in
        *"updated."*) pass ".bat: equal-metadata apply reports success" ;;
        *) fail ".bat: equal-metadata apply did not report success" ;;
    esac
    if diff -q "$bat_equal_source" "$bat_equal_dest" >/dev/null; then
        pass ".bat: equal-metadata apply replaces stale bytes"
    else
        fail ".bat: equal-metadata apply left stale bytes"
    fi

    echo "[.bat] dry run reports CRLF-only drift"
    bat_skill="$HOME_BAT/.claude/skills/demoskill/SKILL.md"
    sed 's/\r$//; s/$/\r/' "$SRC2/demoskill/SKILL.md" > "$bat_skill.crlf"
    mv "$bat_skill.crlf" "$bat_skill"
    if diff -q --strip-trailing-cr "$SRC2/demoskill/SKILL.md" "$bat_skill" >/dev/null; then
        pass ".bat: CRLF fixture has equivalent text content"
    else
        fail ".bat: CRLF fixture content differs"
    fi
    bat_crlf_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -n --claude demoskill 2>&1)"
    bat_crlf_rc=$?
    if [ "$bat_crlf_rc" -eq 0 ]; then pass ".bat: CRLF-only dry run exits 0"; else fail ".bat: CRLF-only dry run exit $bat_crlf_rc"; fi
    case "$bat_crlf_out" in
        *"update demoskill"*) pass ".bat: CRLF-only drift reports an update" ;;
        *) fail ".bat: CRLF-only drift did not report an update" ;;
    esac
    case "$bat_crlf_out" in
        *"~ SKILL.md (changed)"*) pass ".bat: CRLF-only drift appears in preview" ;;
        *) fail ".bat: CRLF-only drift missing from preview" ;;
    esac

    echo "[.bat] dry run retains structural drift"
    mkdir -p "$HOME_BAT/.claude/skills/demoskill/empty-stale"
    bat_empty_dir_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -n --claude demoskill 2>&1)"
    bat_empty_dir_rc=$?
    if [ "$bat_empty_dir_rc" -eq 0 ]; then pass ".bat: structural dry run exits 0"; else fail ".bat: structural dry run exit $bat_empty_dir_rc"; fi
    case "$bat_empty_dir_out" in
        *"update demoskill"*) pass ".bat: extra empty directory reports an update" ;;
        *) fail ".bat: extra empty directory did not report an update" ;;
    esac
    rmdir "$HOME_BAT/.claude/skills/demoskill/empty-stale"

    echo "[.bat] dry run preserves content drift preview"
    printf '%s\n' "BATCH-CONTENT-DRIFT" >> "$SRC2/demoskill/SKILL.md"
    printf '%s\n' "added" > "$SRC2/demoskill/references/added.md"
    ( cd "$SRC2/demoskill" && git add SKILL.md references/added.md )
    printf '%s\n' "stale" > "$HOME_BAT/.claude/skills/demoskill/references/stale.md"
    bat_preview_out="$(USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -n --claude demoskill 2>&1)"
    bat_preview_rc=$?
    if [ "$bat_preview_rc" -eq 0 ]; then pass ".bat: content drift dry run exits 0"; else fail ".bat: content drift dry run exit $bat_preview_rc"; fi
    case "$bat_preview_out" in
        *"~ SKILL.md (changed)"*) pass ".bat: changed file remains in preview" ;;
        *) fail ".bat: changed file missing from preview" ;;
    esac
    case "$bat_preview_out" in
        *"+ references\\added.md (new)"*) pass ".bat: new file remains in preview" ;;
        *) fail ".bat: new file missing from preview" ;;
    esac
    case "$bat_preview_out" in
        *"- references\\stale.md (removed, no longer shipped)"*) pass ".bat: removed file remains in preview" ;;
        *) fail ".bat: removed file missing from preview" ;;
    esac

    echo "[.bat] cleanup of prior-install cruft"
    mkdir -p "$HOME_BAT/.claude/skills/demoskill/reports"
    echo stale > "$HOME_BAT/.claude/skills/demoskill/reports/old.txt"
    USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude demoskill >/dev/null
    assert_absent ".bat: stale reports/ purged" "$HOME_BAT/.claude/skills/demoskill/reports"

    echo "[.bat] comparison infrastructure failure is fatal"
    stub_git="$WORK/stub_git"; mkdir -p "$stub_git"
    real_git_win="$(cygpath -w "$(command -v git)")"
    # Match `diff` in any position: the installer prefixes global flags
    # (`-c core.autocrlf=false`), so keying on %~1 alone silently stops
    # intercepting and the real git runs, making this test vacuous.
    printf '%s\r\n' '@echo off' 'for %%A in (%*) do if /i "%%~A"=="diff" exit /b 2' \
        "\"$real_git_win\" %*" 'exit /b %errorlevel%' > "$stub_git/git.cmd"
    touch -t 203101010101 "$SRC2/demoskill/SKILL.md"
    bat_compare_failure_out="$(PATH="$stub_git:$PATH" USERPROFILE="$HOME_BAT_WIN" \
        SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" --check --claude demoskill 2>&1)"
    bat_compare_failure_rc=$?
    if [ "$bat_compare_failure_rc" -ne 0 ]; then pass ".bat: comparison failure exits nonzero"; else fail ".bat: comparison failure exit $bat_compare_failure_rc"; fi
    case "$bat_compare_failure_out" in
        *"could not compare demoskill"*) pass ".bat: comparison failure is reported" ;;
        *) fail ".bat: comparison failure was not reported" ;;
    esac

    echo "[.bat] Hermes install and read-only check"
    HOME_HERMES="$WORK/home_hermes"; mkdir -p "$HOME_HERMES"
    HOME_HERMES_WIN="$(cygpath -w "$HOME_HERMES")"
    USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --hermes demoskill >/dev/null
    bat_install_rc=$?
    if [ "$bat_install_rc" -eq 0 ]; then pass ".bat: --hermes installs cleanly"; else fail ".bat: --hermes install exit $bat_install_rc"; fi
    assert_install ".bat Hermes" "$HOME_HERMES/skills"

    echo "[.bat] source enumeration failure preserves installed destination"
    failure_snapshot="$WORK/demoskill-before-source-failure"
    cp -a "$HOME_HERMES/skills/demoskill" "$failure_snapshot"
    mv "$SRC2/demoskill/.git/HEAD" "$SRC2/demoskill/.git/HEAD.broken"
    USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --hermes demoskill >/dev/null 2>&1
    bat_source_failure_rc=$?
    if [ "$bat_source_failure_rc" -ne 0 ]; then pass ".bat: source enumeration failure is fatal"; else fail ".bat: source enumeration failure exit $bat_source_failure_rc"; fi
    assert_tree_matches ".bat: source enumeration failure preserves complete destination tree" \
        "$failure_snapshot" "$HOME_HERMES/skills/demoskill"
    mv "$SRC2/demoskill/.git/HEAD.broken" "$SRC2/demoskill/.git/HEAD"

    echo "[.bat] fatal staging failure skips debugger setup"
    add_debugger_fixture "$SRC2"
    DEBUGGER_MARKER="$WORK/debugger-setup-ran"
    DEBUGGER_MARKER_WIN="$(cygpath -w "$DEBUGGER_MARKER")"
    DEBUGGER_MARKER="$DEBUGGER_MARKER_WIN" \
        USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --hermes --setup-debuggers demoskill using-a-debugger >/dev/null
    bat_debugger_fixture_rc=$?
    if [ "$bat_debugger_fixture_rc" -eq 0 ]; then pass ".bat: debugger fixture installs cleanly"; else fail ".bat: debugger fixture install exit $bat_debugger_fixture_rc"; fi
    assert_exists ".bat: normal install runs debugger setup" "$DEBUGGER_MARKER"
    rm -f "$WORK/debugger-setup-ran"
    mv "$SRC2/demoskill/.git/HEAD" "$SRC2/demoskill/.git/HEAD.broken"
    DEBUGGER_MARKER="$DEBUGGER_MARKER_WIN" \
        USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --hermes --setup-debuggers demoskill using-a-debugger >/dev/null 2>&1
    bat_fatal_debugger_rc=$?
    mv "$SRC2/demoskill/.git/HEAD.broken" "$SRC2/demoskill/.git/HEAD"
    if [ "$bat_fatal_debugger_rc" -ne 0 ]; then pass ".bat: fatal source failure exits nonzero with debugger setup requested"; else fail ".bat: fatal source failure exit $bat_fatal_debugger_rc"; fi
    assert_absent ".bat: fatal source failure skips debugger setup" "$DEBUGGER_MARKER"

    USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" --check --hermes demoskill >/dev/null
    bat_clean_check_rc=$?
    if [ "$bat_clean_check_rc" -eq 0 ]; then pass ".bat: clean Hermes check exits 0"; else fail ".bat: clean Hermes check exit $bat_clean_check_rc"; fi

    before_check="$(cat "$HOME_HERMES/skills/demoskill/SKILL.md")"
    printf '%s\n' "BATCH-CHECK-DRIFT" >> "$SRC2/demoskill/SKILL.md"
    USERPROFILE="$HOME_HERMES_WIN" HERMES_HOME="$HOME_HERMES_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" --check --hermes demoskill >/dev/null
    bat_drift_check_rc=$?
    if [ "$bat_drift_check_rc" -eq 1 ]; then pass ".bat: drifted Hermes check exits 1"; else fail ".bat: drifted Hermes check exit $bat_drift_check_rc"; fi
    if [ "$(cat "$HOME_HERMES/skills/demoskill/SKILL.md")" = "$before_check" ]; then
        pass ".bat: drifted Hermes check does not write"
    else
        fail ".bat: drifted Hermes check modified destination"
    fi

    echo "[.bat] hook registration with --hooks"
    add_hook_skill_fixture "$SRC2"
    USERPROFILE="$HOME_BAT_WIN" SKILLS_SRC_ROOT="$SRC2_WIN" MSYS_NO_PATHCONV=1 \
        cmd.exe /c "$(cygpath -w "$REPO_ROOT/install-skills.bat")" -y --claude --hooks project-lock >/dev/null
    assert_exists ".bat: project-lock hook shipped" "$HOME_BAT/.claude/skills/project-lock/hooks/pre_tool_use.py"
    assert_exists ".bat: claude settings.json created" "$HOME_BAT/.claude/settings.json"
    assert_contains ".bat: pre_tool_use registered in settings.json" "$HOME_BAT/.claude/settings.json" "pre_tool_use.py"
    assert_exists ".bat: hook decisions file created" "$HOME_BAT/.claude/skills/.hook-decisions.json"
    assert_contains ".bat: hook decision recorded" "$HOME_BAT/.claude/skills/.hook-decisions.json" "project-lock/pre_tool_use"
else
    echo "[.bat] skipped (no cmd.exe on this platform)"
fi

echo
if [ "$FAILED" = 0 ]; then echo "ALL TESTS PASSED"; else echo "TESTS FAILED"; fi
exit "$FAILED"
