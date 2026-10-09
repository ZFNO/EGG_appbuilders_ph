@echo off
REM ============================================================
REM  commit.bat - sync the build log, then commit & push.
REM  Run this whenever you want to snapshot your progress.
REM ============================================================
setlocal
cd /d "%~dp0"

echo [log] running sync cycle...
python watcher.py --once
if errorlevel 1 echo [warn] sync reported a problem - continuing anyway

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "log: sync %DATE% %TIME%"
  git push
  echo [ok] committed and pushed
) else (
  echo [ok] nothing to commit
)

echo.
echo [done] press any key to close
pause >nul
endlocal
