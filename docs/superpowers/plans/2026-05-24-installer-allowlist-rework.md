# Installer Allowlist Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the installer's failing exclude-list with a git-native top-level allowlist so generated junk (`__pycache__` etc.) can never ship, and make every install a true mirror that purges cruft left by prior installs.

**Architecture:** For each skill, derive the file set from `git -C <skill> ls-files` (tracked files only — untracked junk is structurally excluded), filter to a top-level allowlist (`SKILL.md` + `scripts/` + `references/` + `assets/` plus extras from an optional `.skillpack` manifest), copy the surviving tracked paths from the working tree into a temp staging dir (so uncommitted edits still install), then mirror staging → destination (removing dest entries absent from staging). Keep dual bash + batch — no Python, since git is already a hard dependency (skills are submodules). `cost-estimator/scripts/` is restructured to runtime-only so the allowlist needs no within-directory pruning.

**Tech Stack:** Bash + Windows batch; `git ls-files`; `cp`/`diff`/`mktemp` (bash) and `robocopy /MIR`/`copy` (batch); pytest (cost-estimator).

---

## Phase 3: `install-skills.bat` parity

### Task 5: Rewrite `install-skills.bat` with the allowlist + staging-mirror

Mirror the bash logic: build a clean staging tree from `git ls-files` filtered to the top-level allowlist, then `robocopy /MIR` staging → dest (no `/XD`, so the dest-pinning bug is gone).

**Files:**
- Modify (full rewrite): `install-skills.bat`

- [x] **Step 1: Replace the entire contents of `install-skills.bat`**

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

- [x] **Step 2: Convert the file to CRLF line endings**

The Write tool emits LF on Windows, which breaks batch `:label` lookup. Run:
```bash
sed -i 's/\r$//; s/$/\r/' install-skills.bat
```
(Strips any existing CR first to avoid doubling, then appends CR to every line.)

- [x] **Step 3: Run the harness — both `.sh` and `.bat` must pass**

Run:
```bash
bash tests/test-install.sh
```
Expected: final line `ALL TESTS PASSED`, exit 0. Every `[.sh]` and `[.bat]` assertion prints `PASS`.

- [x] **Step 4: Commit the batch rewrite**

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
