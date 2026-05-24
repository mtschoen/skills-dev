@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into one or more agent config dirs.
rem
rem Each top-level dir here is a skill submodule with a SKILL.md at its
rem root. Installable content is <skill>\ itself; dev-only files are
rem excluded for the root layout (see EXCLUDE_DIRS / EXCLUDE_FILES).
rem
rem Usage: install-skills.bat [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
rem   -y / --yes       overwrite without prompting
rem   -n / --dry-run   show what would change, don't copy
rem   --agents         install to %%USERPROFILE%%\.agents\skills (canonical source of truth)
rem   --claude         install to %%USERPROFILE%%\.claude\skills (Claude's mirror of .agents\skills)
rem   --gemini         install to %%USERPROFILE%%\.gemini\skills (Antigravity's global skills dir)
rem   --all            install to all known agent skill dirs
rem   positional args  limit to specific skill names (default: all)
rem
rem With no agent flag, installs to .agents\skills plus the two harnesses that
rem can't read it directly: .claude\skills (Claude) and .gemini\skills
rem (Antigravity). Codex reads .agents\skills natively, so it needs no copy.

set "SRC_ROOT=%~dp0"
if "%SRC_ROOT:~-1%"=="\" set "SRC_ROOT=%SRC_ROOT:~0,-1%"

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
if "%DEST_COUNT%"=="0" (
    call :add_dest agents "%USERPROFILE%\.agents\skills"
    call :add_dest claude "%USERPROFILE%\.claude\skills"
    call :add_dest gemini "%USERPROFILE%\.gemini\skills"
)

rem Dev-only files excluded when installing a skill.
set "EXCLUDE_DIRS=.git .github .gitea docs evals node_modules reports tests workspace smoke-test-workspace"
set "EXCLUDE_FILES=.git .gitignore .gitmodules .markdownlint-cli2.jsonc README.md AUDIT.md LICENSE HANDOFF.md capture-screenshot.py regen-screenshots.sh regen-screenshots.bat"

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
set "content_dir="
set "layout="

if exist "!src!\SKILL.md" (
    set "content_dir=!src!"
    set "layout=root"
) else (
    echo skip !n! ^(no SKILL.md^)
    exit /b 0
)

set "dest=!dest_root!\!n!"

if not exist "!dest!" (
    echo install !n! -^> !dest! ^(!agent!^)
    if "!DRY_RUN!"=="1" exit /b 0
    if not exist "!dest_root!" mkdir "!dest_root!"
    call :sync_dir "!content_dir!" "!dest!" "!layout!"
    exit /b 0
)

set "excl="
if "!layout!"=="root" set "excl=/XD !EXCLUDE_DIRS! /XF !EXCLUDE_FILES!"

set "tmpout=%TEMP%\install-skills-!agent!-!n!.txt"
robocopy "!content_dir!" "!dest!" /MIR /L /NJH /NJS /NDL /NP /NS /NC /FP !excl! > "!tmpout!"
set "rc=!errorlevel!"

if !rc! geq 8 (
    echo robocopy /L failed for !n! ^(!agent!, exit !rc!^) 1>&2
    del "!tmpout!" 2>nul
    exit /b 0
)

if !rc! equ 0 (
    echo unchanged !n! ^(!agent!^)
    del "!tmpout!" 2>nul
    exit /b 0
)

echo.
echo update !n! -^> !dest! ^(!agent!, changes below^):
for /f "usebackq delims=" %%L in ("!tmpout!") do echo   %%L
del "!tmpout!" 2>nul

if "!DRY_RUN!"=="1" (
    echo   ^(dry-run; not applying^)
    exit /b 0
)

call :confirm "overwrite !dest!?"
if errorlevel 1 (
    echo   skipped.
    exit /b 0
)
if not exist "!dest_root!" mkdir "!dest_root!"
call :sync_dir "!content_dir!" "!dest!" "!layout!"
echo   updated.
exit /b 0

:sync_dir
set "c=%~1"
set "d=%~2"
set "lay=%~3"
set "excl="
if "!lay!"=="root" set "excl=/XD !EXCLUDE_DIRS! /XF !EXCLUDE_FILES!"
robocopy "!c!" "!d!" /MIR /NJH /NJS /NDL /NP /NS /NC /NFL !excl! >nul
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
echo   --agents         install to %%USERPROFILE%%\.agents\skills ^(canonical source of truth^)
echo   --claude         install to %%USERPROFILE%%\.claude\skills ^(Claude's mirror of .agents\skills^)
echo   --gemini         install to %%USERPROFILE%%\.gemini\skills ^(Antigravity's global skills dir^)
echo   --all            install to all known agent skill dirs
echo   positional args  limit to specific skill names ^(default: all^)
echo.
echo With no agent flag, installs to .agents\skills, .claude\skills, and .gemini\skills.
exit /b 0
