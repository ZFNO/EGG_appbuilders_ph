@echo off
REM Invisible Secretary - local model sidecar launcher.
REM Hosts the on-device Qwen model for the restyled dashboard (no wasm, no cloud).
setlocal
cd /d "%~dp0"

python -c "import onnxruntime, transformers, numpy" 2>nul
if errorlevel 1 (
  echo [sidecar] installing dependencies from requirements.txt ...
  python -m pip install -r requirements.txt
)

python server.py %*
