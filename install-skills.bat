@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into %USERPROFILE%\.claude\skills\.
rem
rem Each top-level dir here is a skill submodule. Installable content is
rem either <skill>\skill-draft\ (legacy layout) or <skill>\ itself (new
rem layout, detected by a SKILL.md at the root). Dev-only files are
rem excluded for the root layout.
rem
rem Usage: install-skills.bat [-y] [-n] [skill ...]
rem   -y / --yes       overwrite without prompting
rem   -n / --dry-run   show what would change, don't copy
rem   positional args  limit to specific skill names (default: all)

set "SRC_ROOT=%~dp0"
if "%SRC_ROOT:~-1%"=="\" set "SRC_ROOT=%SRC_ROOT:~0,-1%"
set "DEST_ROOT=%USERPROFILE%\.claude\skills"

set "ASSUME_YES=0"
set "DRY_RUN=0"
set "SELECTED="

:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="-y"         (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="--yes"      (set "ASSUME_YES=1" & shift & goto parse_args)
if /i "%~1"=="-n"         (set "DRY_RUN=1"    & shift & goto parse_args)
if /i "%~1"=="--dry-run"  (set "DRY_RUN=1"    & shift & goto parse_args)
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

rem Excludes applied only to the root layout.
set "EXCLUDE_DIRS=.git .github docs evals node_modules reports skill-draft tests"
set "EXCLUDE_FILES=.git .gitignore .gitmodules README.md AUDIT.md LICENSE HANDOFF.md capture-screenshot.py regen-screenshots.sh regen-screenshots.bat"

if not exist "%DEST_ROOT%" mkdir "%DEST_ROOT%"

for /d %%D in ("%SRC_ROOT%\*") do (
    set "name=%%~nxD"
    set "src=%%~fD"
    if exist "!src!\.git" call :maybe_install "!name!" "!src!"
)

endlocal
exit /b 0

:maybe_install
call :is_selected "%~1"
if errorlevel 1 exit /b 0
call :install_skill "%~1" "%~2"
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

set "dest=%DEST_ROOT%\!n!"

if not exist "!dest!" (
    echo install !n! -^> !dest!
    if "!DRY_RUN!"=="1" exit /b 0
    call :sync_dir "!content_dir!" "!dest!" "!layout!"
    exit /b 0
)

set "excl="
if "!layout!"=="root" set "excl=/XD !EXCLUDE_DIRS! /XF !EXCLUDE_FILES!"

set "tmpout=%TEMP%\install-skills-!n!.txt"
robocopy "!content_dir!" "!dest!" /MIR /L /NJH /NJS /NDL /NP /NS /NC /FP !excl! > "!tmpout!"
set "rc=!errorlevel!"

if !rc! geq 8 (
    echo robocopy /L failed for !n! ^(exit !rc!^) 1>&2
    del "!tmpout!" 2>nul
    exit /b 0
)

if !rc! equ 0 (
    echo unchanged !n!
    del "!tmpout!" 2>nul
    exit /b 0
)

echo.
echo update !n! ^(changes below^):
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
echo Install skills from this repo into %%USERPROFILE%%\.claude\skills\.
echo.
echo Usage: install-skills.bat [-y] [-n] [skill ...]
echo   -y / --yes       overwrite without prompting
echo   -n / --dry-run   show what would change, don't copy
echo   positional args  limit to specific skill names ^(default: all^)
exit /b 0
