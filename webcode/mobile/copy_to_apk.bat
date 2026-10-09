@echo off
REM =====================================================================
REM  Build the mobile web bundle and copy it into the APK assets folder.
REM  Source: webcode\mobile\dist   ->   apk\app\src\main\assets
REM =====================================================================
setlocal
cd /d "%~dp0"

echo [1/3] installing deps...
call bun install
if errorlevel 1 call npm install

echo [2/3] building mobile bundle...
call bun run build
if errorlevel 1 call npm run build

echo [3/3] copying dist into apk assets...
set "DEST=%~dp0..\..\apk\app\src\main\assets"
if not exist "%DEST%" mkdir "%DEST%"

REM clean stale assets (keep .gitkeep), then copy fresh build
for /f "delims=" %%F in ('dir /b /a-d "%DEST%" ^| findstr /v /i ".gitkeep"') do del /q "%DEST%\%%F"
for /d %%D in ("%DEST%\*") do rd /s /q "%%D"

xcopy /e /y /i "dist\*" "%DEST%\"
if errorlevel 1 (echo [x] copy failed & exit /b 1)

echo [ok] mobile bundle copied to %DEST%
endlocal
