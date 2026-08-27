@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into one or more agent config dirs.
rem Skill source repositories are authoritative; runtime destinations are generated
rem mirrors and must not be edited directly.
rem
rem Each top-level dir here is a skill submodule with a SKILL.md at its root.
rem The installer ships only GIT-TRACKED files (git ls-files), filtered to a
rem top-level allowlist: SKILL.md + scripts\ + references\ + assets\, plus any
rem extra top-level entries listed in the skill's optional .skillpack manifest.
rem Tracked-only shipping means generated junk (e.g. __pycache__) can't leak
rem from source. Each install mirrors a clean staging tree, so files left by
rem older installs are removed -- EXCEPT content created in the DEST by
rem running installed scripts (__pycache__, *.pyc, .pytest_cache), which is
rem preserved and never reported as drift (see ROBO_EXCL below).
rem
rem Usage: install-skills.bat [-y] [-n] [--check] [--agents] [--claude] [--gemini] [--hermes] [--all] [--setup-debuggers] [skill ...]
rem   -y / --yes         overwrite without prompting
rem   -n / --dry-run     show what would change, don't copy
rem   --check            check for drift without prompting or writing (0 clean, 1 drift, 2 argument error)
rem   --agents           install to %%USERPROFILE%%\.agents\skills
rem   --claude           install to %%USERPROFILE%%\.claude\skills
rem   --gemini           install to %%USERPROFILE%%\.gemini\config\skills
rem   --hermes           install to Hermes home (HERMES_HOME, LOCALAPPDATA\hermes, or USERPROFILE\.hermes)
rem   --all              install to all known agent skill dirs
rem   --setup-debuggers  after install, run using-a-debugger's setup-debuggers.py to
rem                      install the debuggers it drives (netcoredbg/cdb/lldb,
rem                      platform-gated, idempotent); honors -n as the script's --dry-run
rem   positional args    limit to specific skill names (default: all)
rem
rem With no agent flag, installs only to harness dirs that ALREADY EXIST on this
rem machine (%USERPROFILE%\.agents, \.claude, \.gemini, Hermes). A destination whose
rem parent dir is absent is skipped, so harnesses you don't use get no phantom
rem dir. Pass explicit --agents/--claude/--gemini/--hermes/--all to create a missing one.
rem
rem Test seam: set SKILLS_SRC_ROOT to override the source dir scanned.

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "SRC_ROOT=%REPO_ROOT%"
if defined SKILLS_SRC_ROOT set "SRC_ROOT=%SKILLS_SRC_ROOT%"

set "ASSUME_YES=0"
set "DRY_RUN=0"
set "CHECK_MODE=0"
set "DRIFT_FOUND=0"
set "DEFAULT_MODE=0"
set "SETUP_DEBUGGERS=0"
set "HOOKS_MODE=0"
set "PRUNE_HOOKS=0"
set "SELECTED="
set "DEST_COUNT=0"
set "ABORT=0"
set "FATAL=0"
set "APPLY_FAILED=0"

rem Destination content to preserve across installs: generated junk created in
rem the DEST by running installed scripts (Python caches). Excluding these from
rem robocopy means /MIR won't delete them and the /L preview won't list them as
rem *EXTRA. Applies to every robocopy call below. No skill may SHIP a top-level
rem entry with one of these names (it would be skipped on install). Skills now
rem write generated output OUTSIDE the install tree (e.g. cost-estimator uses
rem ~/.claude/cost-estimator/), so reports\ no longer needs preserving here.
set "ROBO_EXCL=/XD __pycache__ .pytest_cache /XF *.pyc *.pyo"

:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="-y"         (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="--yes"      (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="-n"         (set "DRY_RUN=1"    & shift & goto parse_args)
if /i "%~1"=="--dry-run"  (set "DRY_RUN=1"    & shift & goto parse_args)
if /i "%~1"=="--check"    (set "CHECK_MODE=1" & set "DRY_RUN=1" & set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="--agents"   (call :add_dest agents "%USERPROFILE%\.agents\skills" & shift & goto parse_args)
if /i "%~1"=="--claude"   (call :add_dest claude "%USERPROFILE%\.claude\skills" & shift & goto parse_args)
if /i "%~1"=="--gemini"   (call :add_dest gemini "%USERPROFILE%\.gemini\config\skills" & shift & goto parse_args)
if /i "%~1"=="--hermes"   (call :set_hermes_home & call :add_dest hermes "!HERMES_SKILLS!" & shift & goto parse_args)
if /i "%~1"=="--all"      (call :add_all_dests & shift & goto parse_args)
if /i "%~1"=="--setup-debuggers" (set "SETUP_DEBUGGERS=1" & shift & goto parse_args)
if /i "%~1"=="--hooks"        (set "HOOKS_MODE=1" & shift & goto parse_args)
if /i "%~1"=="--prune-hooks"  (set "PRUNE_HOOKS=1" & shift & goto parse_args)
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
if "%DEST_COUNT%"=="0" (
    set "DEFAULT_MODE=1"
    call :add_all_dests
)
if "!DEFAULT_MODE!"=="1" if "!DEST_COUNT!"=="0" (
    echo No existing skill destinations on this machine. Pass --agents/--claude/--gemini/--hermes or --all to bootstrap one.
    endlocal
    exit /b 0
)

set "BASELINE= SKILL.md scripts references assets "

set "SKILL_COUNT=0"
set "FOUND=0"
set "USING_A_DEBUGGER_SOURCE="
call :discover_skills
for /l %%I in (1,1,!SKILL_COUNT!) do (
    if "!ABORT!"=="1" if not "!FATAL!"=="1" exit /b 0
    call :maybe_install "!SKILL_NAME_%%I!" "!SKILL_PATH_%%I!"
    set /a FOUND+=1
)

if "!FOUND!"=="0" (
    echo warning: no installable skills found under %SRC_ROOT%. 1>&2
    echo          are you sure SKILL.md files are present under this tree? 1>&2
    endlocal
    exit /b 1
)

if "!ABORT!"=="1" (
    echo.
    echo aborted by user ^(q^); remaining skills skipped.
)

if "!SETUP_DEBUGGERS!"=="1" if "!CHECK_MODE!"=="0" if not "!ABORT!"=="1" if not "!FATAL!"=="1" if not "!APPLY_FAILED!"=="1" call :setup_debuggers
if "!HOOKS_MODE!"=="1" if not "!ABORT!"=="1" if not "!FATAL!"=="1" if not "!APPLY_FAILED!"=="1" call :manage_hooks
if "!PRUNE_HOOKS!"=="1" if not "!ABORT!"=="1" if not "!FATAL!"=="1" if not "!APPLY_FAILED!"=="1" call :manage_hooks

if "!FATAL!"=="1" (
    endlocal
    exit /b 1
)
if "!APPLY_FAILED!"=="1" (
    echo.
    echo one or more skills failed to install; see the errors above. 1>&2
    endlocal
    exit /b 1
)
if "!CHECK_MODE!"=="1" if "!DRIFT_FOUND!"=="1" (
    endlocal
    exit /b 1
)

endlocal
exit /b 0

:setup_debuggers
rem Install the debuggers using-a-debugger drives. Deps are machine-global, so
rem this runs once from the source tree regardless of destination count. Opt-in
rem via --setup-debuggers so a routine skill copy never triggers an install.
if not defined USING_A_DEBUGGER_SOURCE (
    set "setup_script="
) else (
    set "setup_script=!USING_A_DEBUGGER_SOURCE!\scripts\setup-debuggers.py"
)
call :is_selected using-a-debugger
if errorlevel 1 (
    echo.
    echo --setup-debuggers: skipped ^(using-a-debugger not in the selected skills^)
    exit /b 0
)
if not exist "!setup_script!" (
    echo.
    echo --setup-debuggers: skipped ^(!setup_script! not found^) 1>&2
    exit /b 0
)
set "PYBIN="
where python >nul 2>nul && set "PYBIN=python"
if not defined PYBIN ( where py >nul 2>nul && set "PYBIN=py" )
if not defined PYBIN (
    echo.
    echo --setup-debuggers: skipped ^(no python/py on PATH^) 1>&2
    exit /b 0
)
echo.
echo running debugger dependency setup ^(!setup_script!^)
if "!DRY_RUN!"=="1" (
    "!PYBIN!" "!setup_script!" --dry-run
) else (
    "!PYBIN!" "!setup_script!"
)
exit /b 0

:manage_hooks
set "hooks_script=%REPO_ROOT%\scripts\manage_hooks.py"
if not exist "!hooks_script!" set "hooks_script=%SRC_ROOT%\scripts\manage_hooks.py"
if not exist "!hooks_script!" (
    echo.
    echo --hooks: skipped ^(!hooks_script! not found^) 1>&2
    exit /b 0
)
set "PYBIN="
where python >nul 2>nul && set "PYBIN=python"
if not defined PYBIN ( where py >nul 2>nul && set "PYBIN=py" )
if not defined PYBIN (
    echo.
    echo --hooks: skipped ^(no python/py on PATH^) 1>&2
    exit /b 0
)
echo.
set "HOOK_ARGS="
if "!ASSUME_YES!"=="1" set "HOOK_ARGS=!HOOK_ARGS! -y"
if "!DRY_RUN!"=="1" set "HOOK_ARGS=!HOOK_ARGS! -n"
if "!CHECK_MODE!"=="1" set "HOOK_ARGS=!HOOK_ARGS! --check"
if "!PRUNE_HOOKS!"=="1" set "HOOK_ARGS=!HOOK_ARGS! --prune"
for /l %%I in (1,1,%DEST_COUNT%) do (
    if /i "!DEST_%%I_NAME!"=="claude" set "HOOK_ARGS=!HOOK_ARGS! --claude"
    if /i "!DEST_%%I_NAME!"=="gemini" set "HOOK_ARGS=!HOOK_ARGS! --gemini"
    if /i "!DEST_%%I_NAME!"=="hermes" set "HOOK_ARGS=!HOOK_ARGS! --hermes"
    if /i "!DEST_%%I_NAME!"=="agents" set "HOOK_ARGS=!HOOK_ARGS! --agents"
)
if defined SELECTED set "HOOK_ARGS=!HOOK_ARGS! !SELECTED!"
"!PYBIN!" "!hooks_script!" !HOOK_ARGS!
if errorlevel 1 (
    if "!CHECK_MODE!"=="1" (
        set "DRIFT_FOUND=1"
    ) else (
        set "APPLY_FAILED=1"
    )
)
exit /b 0

:discover_skills
rem Discover one-level and one-level-deep skill directories that contain SKILL.md.
set "SKILL_COUNT=0"
for /d %%D in ("%SRC_ROOT%\*") do (
    set "top_name=%%~nxD"
    set "top_src=%%~fD"
    if not "!ABORT!"=="1" if not "!FATAL!"=="1" (
        if exist "!top_src!\SKILL.md" (
            call :add_discovered_skill "!top_name!" "!top_src!"
        ) else (
            for /d %%C in ("%%~fD\*") do (
                if not "!ABORT!"=="1" if not "!FATAL!"=="1" (
                    if exist "%%~fC\SKILL.md" (
                        call :add_discovered_skill "%%~nxC" "%%~fC"
                    )
                )
            )
        )
    )
)
exit /b 0

:add_discovered_skill
for /l %%I in (1,1,!SKILL_COUNT!) do (
    if /i "!SKILL_NAME_%%I!"=="%~1" exit /b 0
)
set /a SKILL_COUNT+=1
set "SKILL_NAME_!SKILL_COUNT!=%~1"
set "SKILL_PATH_!SKILL_COUNT!=%~2"
if /i "%~1"=="using-a-debugger" set "USING_A_DEBUGGER_SOURCE=%~2"
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
call :maybe_add_one agents "%USERPROFILE%\.agents\skills"
call :maybe_add_one claude "%USERPROFILE%\.claude\skills"
call :maybe_add_one gemini "%USERPROFILE%\.gemini\config\skills"
call :set_hermes_home
call :maybe_add_one hermes "!HERMES_SKILLS!"
exit /b 0

:set_hermes_home
if defined HERMES_HOME (
    set "HERMES_SKILLS=%HERMES_HOME%\skills"
) else if defined LOCALAPPDATA (
    set "HERMES_SKILLS=%LOCALAPPDATA%\hermes\skills"
) else (
    set "HERMES_SKILLS=%USERPROFILE%\.hermes\skills"
)
exit /b 0

:maybe_add_one
rem In default mode (no explicit flag), skip a destination whose parent harness
rem dir (e.g. %USERPROFILE%\.gemini) is absent, so unused harnesses get no
rem phantom skills dir. Explicit flags reach :add_dest directly and create.
if "!DEFAULT_MODE!"=="1" (
    call :parent_dir "%~2" _PARENT
    if not exist "!_PARENT!\" (
        echo skip %~1 ^(harness dir !_PARENT! not present; pass --%~1 or --all to create^)
        exit /b 0
    )
)
call :add_dest %~1 "%~2"
exit /b 0

:parent_dir
rem %~1 = full path; sets the variable named by %~2 to its parent dir (no trailing slash)
for %%P in ("%~1") do set "_pd=%%~dpP"
if "!_pd:~-1!"=="\" set "_pd=!_pd:~0,-1!"
set "%~2=!_pd!"
exit /b 0

:maybe_install
call :is_selected "%~1"
if errorlevel 1 exit /b 0
for /l %%I in (1,1,%DEST_COUNT%) do (
    if not "!ABORT!"=="1" if not "!FATAL!"=="1" call :install_skill "%~1" "%~2" "!DEST_%%I_NAME!" "!DEST_%%I_PATH!"
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
if errorlevel 1 (
    echo staging failed for !n! ^(!agent!^); destination was not changed. 1>&2
    if exist "!staging!" rmdir /s /q "!staging!"
    set "FATAL=1"
    exit /b 1
)

if not exist "!dest!" (
    echo install !n! -^> !dest! ^(!agent!^)
    if "!CHECK_MODE!"=="1" set "DRIFT_FOUND=1"
    if "!DRY_RUN!"=="1" ( rmdir /s /q "!staging!" & exit /b 0 )
    if not exist "!dest_root!" mkdir "!dest_root!"
    robocopy "!staging!" "!dest!" /MIR !ROBO_EXCL! /NJH /NJS /NDL /NP /NS /NC /NFL >nul
    set "rc=!errorlevel!"
    rmdir /s /q "!staging!"
    if !rc! geq 8 (
        echo   FAILED to install !n! at !dest! ^(robocopy exit !rc!^) 1>&2
        set "APPLY_FAILED=1"
        exit /b 1
    )
    exit /b 0
)

set "tmpout=%TEMP%\install-skills-!agent!-!n!.txt"
set "preview=%TEMP%\install-skills-preview-!agent!-!n!.txt"
rem Include every source-side metadata class; :fmt_line decides by byte content.
robocopy "!staging!" "!dest!" /MIR /L !ROBO_EXCL! /IS /IT /IM /NJH /NJS /NDL /NP /NS /FP > "!tmpout!"
set "rc=!errorlevel!"

if !rc! geq 8 (
    echo robocopy /L failed for !n! ^(!agent!, exit !rc!^) 1>&2
    del "!tmpout!" 2>nul
    del "!preview!" 2>nul
    rmdir /s /q "!staging!"
    set "FATAL=1"
    exit /b 0
)

set "COMPARE_FOUND=0"
set "COMPARE_FAILED=0"
set /a "ROBO_EXTRA=rc & 2"
del "!preview!" 2>nul
for /f "usebackq delims=" %%L in ("!tmpout!") do call :fmt_line "!staging!" "!dest!" "%%L" >> "!preview!"
del "!tmpout!" 2>nul
if not "!ROBO_EXTRA!"=="0" set "COMPARE_FOUND=1"

if "!COMPARE_FAILED!"=="1" (
    echo could not compare !n! at !dest! 1>&2
    del "!preview!" 2>nul
    rmdir /s /q "!staging!"
    set "FATAL=1"
    exit /b 0
)

if "!COMPARE_FOUND!"=="0" (
    echo unchanged !n! ^(!agent!^)
    del "!preview!" 2>nul
    rmdir /s /q "!staging!"
    exit /b 0
)

echo.
echo update !n! -^> !dest! ^(!agent!^)
if exist "!preview!" type "!preview!"
del "!preview!" 2>nul

if "!CHECK_MODE!"=="1" set "DRIFT_FOUND=1"

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
robocopy "!staging!" "!dest!" /MIR !ROBO_EXCL! /IS /IT /IM /NJH /NJS /NDL /NP /NS /NC /NFL >nul
set "rc=!errorlevel!"
rmdir /s /q "!staging!"
if !rc! geq 8 (
    echo   FAILED to update !n! at !dest! - it may be partially written ^(robocopy exit !rc!^) 1>&2
    set "APPLY_FAILED=1"
    exit /b 1
)
echo   updated.
exit /b 0

:fmt_line
rem %1=staging dir, %2=dest dir, %3=one raw robocopy /L line. Emit a
rem git-status-style line (+ new / ~ changed / - removed) with the absolute
rem prefix stripped to a skill-relative path. Robocopy /FP prints the staging
rem (TEMP) path for source-side classes and the dest path for *EXTRA File
rem (dest-only -> would be removed by /MIR). Stripping the prefix keeps the
rem TEMP staging dir out of the user-facing preview.
rem Robocopy classifies files by metadata, so verify source-side candidates by
rem byte-exact content before reporting them, matching the shell installer.
set "_st=%~1"
set "_de=%~2"
set "_ln=%~3"
set "_rel="
set "_sym="
set "_note="
set "_after=!_ln:*%_st%\=!"
if not "!_after!"=="!_ln!" (
    set "_rel=!_after!"
    if not exist "!_de!\!_rel!" (
        set "_sym=+"
        set "_note=new"
    ) else (
        rem The installer mirrors bytes, so the comparison must be byte-exact.
        rem core.autocrlf=true (the Git for Windows default) makes git diff
        rem normalize line endings and report a CRLF-vs-LF destination as
        rem identical, so drift would never be re-synced. Pin it off here.
        rem `call` because git may resolve to a git.cmd shim, and a batch file
        rem invoking another batch file without `call` transfers control away
        rem and never returns - this script would exit mid-run.
        call git -c core.autocrlf=false diff --no-index --quiet --no-ext-diff --no-textconv -- "!_st!\!_rel!" "!_de!\!_rel!" >nul 2>nul
        set "_compare_rc=!errorlevel!"
        if "!_compare_rc!"=="0" exit /b 0
        if not "!_compare_rc!"=="1" (
            set "COMPARE_FAILED=1"
            exit /b 0
        )
        set "_sym=~"
        set "_note=changed"
    )
) else (
    set "_after=!_ln:*%_de%\=!"
    if not "!_after!"=="!_ln!" (set "_rel=!_after!" & set "_sym=-" & set "_note=removed, no longer shipped")
)
if defined _rel (
    set "COMPARE_FOUND=1"
    echo   !_sym! !_rel! ^(!_note!^)
)
exit /b 0

:build_staging
set "bs_src=%~1"
set "bs_staging=%~2"
set "bs_listing=!bs_staging!\.tracked-files.txt"
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
rem Capture enumeration first: for /f does not expose the command's exit code.
rem `call` guards the same git.cmd-shim control transfer described above; without
rem it a shim would end this script before the exit-code check below ever runs.
call git -C "!bs_src!" ls-files > "!bs_listing!"
set "bs_rc=!errorlevel!"
if not "!bs_rc!"=="0" (
    echo git ls-files failed for !bs_src! ^(exit !bs_rc!^) 1>&2
    del "!bs_listing!" 2>nul
    rmdir /s /q "!bs_staging!"
    exit /b 1
)
rem copy each tracked file whose top-level component is in the include set
for /f "usebackq delims=" %%F in ("!bs_listing!") do (
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
del "!bs_listing!" 2>nul
exit /b 0

:confirm
if "!ASSUME_YES!"=="1" exit /b 0
set "reply=__NOPROMPT__"
set /p "reply=%~1 [y/N/q=quit] "
if "!reply!"=="__NOPROMPT__" (
    echo   ^(no tty; skipping. re-run with -y to overwrite.^) 1>&2
    exit /b 1
)
if /i "!reply!"=="q" (set "ABORT=1" & exit /b 1)
if /i "!reply!"=="y" exit /b 0
exit /b 1

:usage
echo Install skills from this repo into one or more agent config dirs.
echo.
echo Usage: install-skills.bat [-y] [-n] [--check] [--agents] [--claude] [--gemini] [--hermes] [--all] [--setup-debuggers] [--hooks] [--prune-hooks] [skill ...]
echo   -y / --yes         overwrite without prompting
echo   -n / --dry-run     show what would change, don't copy
echo   --check            check for drift without prompting or writing ^(0 clean, 1 drift, 2 argument error^)
echo   --agents           install to %%USERPROFILE%%\.agents\skills
echo   --claude           install to %%USERPROFILE%%\.claude\skills
echo   --gemini           install to %%USERPROFILE%%\.gemini\config\skills
echo   --hermes           install to Hermes home ^(HERMES_HOME, LOCALAPPDATA\hermes, or USERPROFILE\.hermes^)
echo   --all              install to all known agent skill dirs
echo   --setup-debuggers  after install, run using-a-debugger's setup-debuggers.py
echo   --hooks            check and offer to register hooks in harness settings
echo   --prune-hooks      prune dangling hook entries pointing to uninstalled skill files
echo   positional args    limit to specific skill names ^(default: all^)
exit /b 0
