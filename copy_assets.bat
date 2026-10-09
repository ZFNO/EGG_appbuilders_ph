@echo off
setlocal
cd /d "%~dp0"
set "SRC=webcode\mobile\dist"
set "DEST=apk\app\src\main\assets"
if not exist "%DEST%" mkdir "%DEST%"
for %%F in ("%DEST%\*") do if /i not "%%~nxF"==".gitkeep" del /q "%%F" >nul 2>&1
for /d %%D in ("%DEST%\*") do rd /s /q "%%D" >nul 2>&1
robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS
echo ROBO_EXIT=%ERRORLEVEL%
echo ---TOP---
dir /b "%DEST%"
echo ---MODEL---
dir /s /b "%DEST%\models" | findstr /i "model_q4.onnx"
echo ---ORT---
dir /b "%DEST%\ort"
