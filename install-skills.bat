@echo off
setlocal enabledelayedexpansion

rem Install skills from this repo into one or more agent config dirs.
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
rem Usage: install-skills.bat [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
rem   -y / --yes       overwrite without prompting
rem   -n / --dry-run   show what would change, don't copy
rem   --agents         install to %%USERPROFILE%%\.agents\skills
rem   --claude         install to %%USERPROFILE%%\.claude\skills
rem   --gemini         install to %%USERPROFILE%%\.gemini\config\skills
rem   --all            install to all known agent skill dirs
rem   positional args  limit to specific skill names (default: all)
rem
rem With no agent flag, installs only to harness dirs that ALREADY EXIST on this
rem machine (%USERPROFILE%\.agents, \.claude, \.gemini). A destination whose
rem parent dir is absent is skipped, so harnesses you don't use get no phantom
rem dir. Pass explicit --agents/--claude/--gemini/--all to create a missing one.
rem
rem Test seam: set SKILLS_SRC_ROOT to override the source dir scanned.

set "SRC_ROOT=%~dp0"
if "%SRC_ROOT:~-1%"=="\" set "SRC_ROOT=%SRC_ROOT:~0,-1%"
if defined SKILLS_SRC_ROOT set "SRC_ROOT=%SKILLS_SRC_ROOT%"

set "ASSUME_YES=0"
set "DRY_RUN=0"
set "DEFAULT_MODE=0"
set "SELECTED="
set "DEST_COUNT=0"
set "ABORT=0"

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
if /i "%~1"=="--agents"   (call :add_dest agents "%USERPROFILE%\.agents\skills" & shift & goto parse_args)
if /i "%~1"=="--claude"   (call :add_dest claude "%USERPROFILE%\.claude\skills" & shift & goto parse_args)
if /i "%~1"=="--gemini"   (call :add_dest gemini "%USERPROFILE%\.gemini\config\skills" & shift & goto parse_args)
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
    set "DEFAULT_MODE=1"
    call :add_all_dests
)
if "!DEFAULT_MODE!"=="1" if "!DEST_COUNT!"=="0" (
    echo No existing skill destinations on this machine. Pass --agents/--claude/--gemini or --all to bootstrap one.
    endlocal
    exit /b 0
)

set "BASELINE= SKILL.md scripts references assets "

set "FOUND=0"
for /d %%D in ("%SRC_ROOT%\*") do (
    if not "!ABORT!"=="1" (
        set "name=%%~nxD"
        set "src=%%~fD"
        if exist "!src!\.git" (
            set /a FOUND+=1
            call :maybe_install "!name!" "!src!"
        )
    )
)

if "!FOUND!"=="0" (
    echo warning: no skill submodules found under %SRC_ROOT%. 1>&2
    echo          did you forget to run 'git submodule update --init --recursive'? 1>&2
    endlocal
    exit /b 1
)

if "!ABORT!"=="1" (
    echo.
    echo aborted by user ^(q^); remaining skills skipped.
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
call :maybe_add_one agents "%USERPROFILE%\.agents\skills"
call :maybe_add_one claude "%USERPROFILE%\.claude\skills"
call :maybe_add_one gemini "%USERPROFILE%\.gemini\config\skills"
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
    if not "!ABORT!"=="1" call :install_skill "%~1" "%~2" "!DEST_%%I_NAME!" "!DEST_%%I_PATH!"
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
    robocopy "!staging!" "!dest!" /MIR !ROBO_EXCL! /NJH /NJS /NDL /NP /NS /NC /NFL >nul
    rmdir /s /q "!staging!"
    exit /b 0
)

set "tmpout=%TEMP%\install-skills-!agent!-!n!.txt"
robocopy "!staging!" "!dest!" /MIR /L !ROBO_EXCL! /NJH /NJS /NDL /NP /NS /FP > "!tmpout!"
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
echo update !n! -^> !dest! ^(!agent!^)
for /f "usebackq delims=" %%L in ("!tmpout!") do call :fmt_line "!staging!" "!dest!" "%%L"
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
robocopy "!staging!" "!dest!" /MIR !ROBO_EXCL! /NJH /NJS /NDL /NP /NS /NC /NFL >nul
echo   updated.
rmdir /s /q "!staging!"
exit /b 0

:fmt_line
rem %1=staging dir, %2=dest dir, %3=one raw robocopy /L line. Emit a
rem git-status-style line (+ new / ~ changed / - removed) with the absolute
rem prefix stripped to a skill-relative path. Robocopy /FP prints the staging
rem (TEMP) path for source-side classes (New File/Newer/Older/Changed) and the
rem dest path for *EXTRA File (dest-only -> would be removed by /MIR). Stripping
rem the prefix keeps the TEMP staging dir out of the user-facing preview.
set "_st=%~1"
set "_de=%~2"
set "_ln=%~3"
set "_rel="
set "_sym="
set "_note="
set "_after=!_ln:*%_st%\=!"
if not "!_after!"=="!_ln!" (
    set "_rel=!_after!"
    if not "!_ln:New File=!"=="!_ln!" (set "_sym=+" & set "_note=new") else (set "_sym=~" & set "_note=changed")
) else (
    set "_after=!_ln:*%_de%\=!"
    if not "!_after!"=="!_ln!" (set "_rel=!_after!" & set "_sym=-" & set "_note=removed, no longer shipped")
)
if defined _rel echo   !_sym! !_rel! ^(!_note!^)
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
echo Usage: install-skills.bat [-y] [-n] [--agents] [--claude] [--gemini] [--all] [skill ...]
echo   -y / --yes       overwrite without prompting
echo   -n / --dry-run   show what would change, don't copy
echo   --agents         install to %%USERPROFILE%%\.agents\skills
echo   --claude         install to %%USERPROFILE%%\.claude\skills
echo   --gemini         install to %%USERPROFILE%%\.gemini\config\skills
echo   --all            install to all known agent skill dirs
echo   positional args  limit to specific skill names ^(default: all^)
exit /b 0
