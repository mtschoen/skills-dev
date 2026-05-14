@echo off
rem Fetch + fast-forward main from origin and optionally one additional remote
rem named with --remote <name> in every active submodule and the skills-dev
rem index. Does not bump submodule pointers.
rem Run from anywhere; the script cd's to the repo root.
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set "REMOTE_COUNT=1"
set "REMOTE_1=origin"

:parse_args
if "%~1"=="" goto parse_done
if /i "%~1"=="--remote" (
  if "%~2"=="" (
    echo --remote requires a value 1>&2
    exit /b 2
  )
  set /a REMOTE_COUNT+=1
  set "REMOTE_!REMOTE_COUNT!=%~2"
  shift
  shift
  goto parse_args
)
if /i "%~1"=="-h" goto usage
if /i "%~1"=="--help" goto usage
echo unknown argument: %~1 1>&2
goto usage_error

:parse_done

for /f "tokens=2" %%P in ('git config --file .gitmodules --get-regexp "submodule\..*\.path"') do (
  if exist "%%P\.git" (
    for /l %%R in (1,1,%REMOTE_COUNT%) do call :pull_one "%%P" "!REMOTE_%%R!"
  ) else (
    echo === %%P ^(not initialized, skipping^) ===
  )
)

for /l %%R in (1,1,%REMOTE_COUNT%) do call :pull_one "." "!REMOTE_%%R!"
goto :eof

:pull_one
set DIR=%~1
set REMOTE=%~2
git -C "%DIR%" remote get-url %REMOTE% >nul 2>&1
if errorlevel 1 goto :eof
echo === %DIR% ^(%REMOTE%^) ===
git -C "%DIR%" fetch %REMOTE%
if errorlevel 1 (
  echo   FAILED: fetch
  goto :eof
)
git -C "%DIR%" merge --ff-only %REMOTE%/main
if errorlevel 1 echo   ^(not fast-forwardable; resolve manually^)
goto :eof

:usage
echo Usage: scripts\pull-all.bat [--remote ^<name^>]
echo.
echo Fetch + fast-forward main from origin in every active submodule plus skills-dev
echo itself. If --remote is provided, also fetch + fast-forward from that remote
echo where it exists.
exit /b 0

:usage_error
call :usage
exit /b 2
