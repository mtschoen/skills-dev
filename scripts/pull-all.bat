@echo off
rem Fetch + fast-forward main from `origin` (Gitea) in every active submodule
rem and the skills-dev index. Does not bump submodule pointers.
rem Run from anywhere; the script cd's to the repo root.
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

for /f "tokens=2" %%P in ('git config --file .gitmodules --get-regexp "submodule\..*\.path"') do (
  if exist "%%P\.git" (
    call :pull_one "%%P"
  ) else (
    echo === %%P ^(not initialized, skipping^) ===
  )
)

call :pull_one "."
goto :eof

:pull_one
set DIR=%~1
echo === %DIR% ===
git -C "%DIR%" fetch origin
if errorlevel 1 (
  echo   FAILED: fetch
  goto :eof
)
git -C "%DIR%" merge --ff-only origin/main
if errorlevel 1 echo   ^(not fast-forwardable; resolve manually^)
goto :eof
