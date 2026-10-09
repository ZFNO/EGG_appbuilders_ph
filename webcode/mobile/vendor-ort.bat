@echo off
REM Regenerate public/ort from node_modules (onnxruntime-web).
setlocal
cd /d "%~dp0"
if not exist "node_modules\onnxruntime-web\dist" goto :noinstall
if exist "public\ort" rmdir /s /q "public\ort"
mkdir "public\ort"
xcopy /e /i /y "node_modules\onnxruntime-web\dist" "public\ort"
echo [ok] public\ort regenerated from node_modules/onnxruntime-web/dist
goto :eof

:noinstall
echo [err] node_modules/onnxruntime-web/dist missing - run "bun install" first.
exit /b 1
