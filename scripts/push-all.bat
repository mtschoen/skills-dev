@echo off
rem Push every active submodule + skills-dev itself to origin and optionally
rem one additional remote named with --remote <name>. Each push is pre-flighted:
rem fetch the remote and classify local main vs remote/main as up-to-date / FF /
rem behind / diverged. A non-FF state is reported with a clear reason instead of
rem a generic "FAILED" line. Errors don't halt the run, but the script exits
rem non-zero with a summary if any push had a problem.
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

set "FAILFILE=%TEMP%\push-all-failures-%RANDOM%.txt"
if exist "%FAILFILE%" del "%FAILFILE%"

for /f "tokens=2" %%P in ('git config --file .gitmodules --get-regexp "submodule\..*\.path"') do (
  echo === %%P ===
  if exist "%%P\.git" (
    for /l %%R in (1,1,%REMOTE_COUNT%) do call :push_one "%%P" "!REMOTE_%%R!"
  ) else (
    echo   ^(not initialized, skipping^)
  )
)

echo === skills-dev ^(index^) ===
for /l %%R in (1,1,%REMOTE_COUNT%) do call :push_one "." "!REMOTE_%%R!"

echo.
echo === Summary ===
if not exist "%FAILFILE%" (
  echo All pushes succeeded or already up-to-date.
  exit /b 0
)
for /f %%C in ('find /c /v "" ^< "%FAILFILE%"') do set FAILCOUNT=%%C
echo !FAILCOUNT! issue^(s^):
type "%FAILFILE%"
del "%FAILFILE%"
exit /b 1

:push_one
set DIR=%~1
set REMOTE=%~2
git -C "%DIR%" remote get-url %REMOTE% >nul 2>&1
if errorlevel 1 goto :eof
echo   -^> %REMOTE%
git -C "%DIR%" fetch %REMOTE% --quiet >nul 2>&1
if errorlevel 1 (
  echo      fetch failed ^(network/auth^)
  echo   %DIR% -^> %REMOTE% ^(fetch failed^)>> "%FAILFILE%"
  goto :eof
)
set AHEAD=
set BEHIND=
for /f "tokens=1,2" %%A in ('git -C "%DIR%" rev-list --left-right --count "main...refs/remotes/%REMOTE%/main" 2^>nul') do (
  set AHEAD=%%A
  set BEHIND=%%B
)
if "!AHEAD!"=="" (
  echo      could not compare local main with %REMOTE%/main
  echo   %DIR% -^> %REMOTE% ^(compare failed^)>> "%FAILFILE%"
  goto :eof
)
if "!AHEAD!"=="0" if "!BEHIND!"=="0" (
  echo      up-to-date
  goto :eof
)
if "!AHEAD!"=="0" (
  echo      behind by !BEHIND! ^(skipping push; pull first^)
  echo   %DIR% -^> %REMOTE% ^(behind by !BEHIND!^)>> "%FAILFILE%"
  goto :eof
)
if not "!BEHIND!"=="0" (
  echo      DIVERGED: ahead !AHEAD!, behind !BEHIND! ^(skipping push; merge first^)
  echo   %DIR% -^> %REMOTE% ^(diverged: ahead !AHEAD!, behind !BEHIND!^)>> "%FAILFILE%"
  goto :eof
)
git -C "%DIR%" push %REMOTE% main
if errorlevel 1 echo   %DIR% -^> %REMOTE% ^(push failed^)>> "%FAILFILE%"
goto :eof

:usage
echo Usage: scripts\push-all.bat [--remote ^<name^>]
echo.
echo Push every active submodule plus skills-dev itself to origin. If --remote is
echo provided, also push to that remote where it exists.
exit /b 0

:usage_error
call :usage
exit /b 2
