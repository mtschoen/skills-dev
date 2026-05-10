@echo off
rem Push every active submodule + skills-dev itself to both `origin` (Gitea)
rem and `github` (GitHub). Each push is pre-flighted: fetch the remote and
rem classify local main vs remote/main as up-to-date / FF / behind / diverged.
rem A non-FF state is reported with a clear reason instead of a generic
rem "FAILED" line. Errors don't halt the run, but the script exits non-zero
rem with a summary if any push had a problem.
rem Run from anywhere; the script cd's to the repo root.
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set "FAILFILE=%TEMP%\push-all-failures-%RANDOM%.txt"
if exist "%FAILFILE%" del "%FAILFILE%"

for /f "tokens=2" %%P in ('git config --file .gitmodules --get-regexp "submodule\..*\.path"') do (
  echo === %%P ===
  if exist "%%P\.git" (
    call :push_one "%%P" origin
    call :push_one "%%P" github
  ) else (
    echo   ^(not initialized, skipping^)
  )
)

echo === skills-dev ^(index^) ===
call :push_one "." origin
call :push_one "." github

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
