@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into one or more agent config dirs.
rem
rem Each top-level dir here is a skill submodule. Installable content is
rem either <skill>\skill-draft\ (legacy layout) or <skill>\ itself (new
rem layout, detected by a SKILL.md at the root). Dev-only files are
rem excluded for the root layout.
rem
rem Usage: install-skills.bat [-y] [-n] [--claude] [--pi] [--hermes] [--gemini] [--codex] [--all] [skill ...]
rem   -y / --yes       overwrite without prompting
rem   -n / --dry-run   show what would change, don't copy
rem   --claude         install to %%USERPROFILE%%\.claude\skills (default when no agent flag is given)
rem   --pi             install to %%USERPROFILE%%\.pi\agent\skills
rem   --hermes         install to %%USERPROFILE%%\.hermes\skills
rem   --gemini         install to %%USERPROFILE%%\.gemini\skills
rem   --codex          install to %%USERPROFILE%%\.codex\skills
rem   --all            install to all known agent skill dirs
rem   positional args  limit to specific skill names (default: all)

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
if /i "%~1"=="--claude"   (call :add_dest claude "%USERPROFILE%\.claude\skills" & shift & goto parse_args)
if /i "%~1"=="--pi"       (call :add_dest pi "%USERPROFILE%\.pi\agent\skills" & shift & goto parse_args)
if /i "%~1"=="--hermes"   (call :add_dest hermes "%USERPROFILE%\.hermes\skills" & shift & goto parse_args)
if /i "%~1"=="--gemini"   (call :add_dest gemini "%USERPROFILE%\.gemini\skills" & shift & goto parse_args)
if /i "%~1"=="--codex"    (call :add_dest codex "%USERPROFILE%\.codex\skills" & shift & goto parse_args)
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
if "%DEST_COUNT%"=="0" call :add_dest claude "%USERPROFILE%\.claude\skills"

rem Excludes applied only to the root layout.
set "EXCLUDE_DIRS=.git .github docs evals node_modules reports skill-draft tests"
set "EXCLUDE_FILES=.git .gitignore .gitmodules README.md AUDIT.md LICENSE HANDOFF.md capture-screenshot.py regen-screenshots.sh regen-screenshots.bat"

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
call :add_dest claude "%USERPROFILE%\.claude\skills"
call :add_dest pi "%USERPROFILE%\.pi\agent\skills"
call :add_dest hermes "%USERPROFILE%\.hermes\skills"
call :add_dest gemini "%USERPROFILE%\.gemini\skills"
call :add_dest codex "%USERPROFILE%\.codex\skills"
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

if exist "!src!\skill-draft\" (
    set "content_dir=!src!\skill-draft"
    set "layout=draft"
) else if exist "!src!\SKILL.md" (
    set "content_dir=!src!"
    set "layout=root"
) else (
    echo skip !n! ^(no SKILL.md and no skill-draft\^)
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
echo Usage: install-skills.bat [-y] [-n] [--claude] [--pi] [--hermes] [--gemini] [--codex] [--all] [skill ...]
echo   -y / --yes       overwrite without prompting
echo   -n / --dry-run   show what would change, don't copy
echo   --claude         install to %%USERPROFILE%%\.claude\skills ^(default when no agent flag is given^)
echo   --pi             install to %%USERPROFILE%%\.pi\agent\skills
echo   --hermes         install to %%USERPROFILE%%\.hermes\skills
echo   --gemini         install to %%USERPROFILE%%\.gemini\skills
echo   --codex          install to %%USERPROFILE%%\.codex\skills
echo   --all            install to all known agent skill dirs
echo   positional args  limit to specific skill names ^(default: all^)
exit /b 0
