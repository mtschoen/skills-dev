@echo off
rem Push every active submodule + skills-dev itself to both `origin` (Gitea)
rem and `github` (GitHub). Errors are printed inline and don't halt the run.
rem Run from anywhere; the script cd's to the repo root.
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

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
goto :eof

:push_one
set DIR=%~1
set REMOTE=%~2
git -C "%DIR%" remote | findstr /x "%REMOTE%" >nul
if errorlevel 1 goto :eof
echo   -^> %REMOTE%
git -C "%DIR%" push %REMOTE% main
if errorlevel 1 echo   FAILED: %DIR% -^> %REMOTE%
goto :eof
