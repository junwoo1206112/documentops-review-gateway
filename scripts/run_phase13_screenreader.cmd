@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [.venv not found] Run: python -m venv .venv ^&^& .venv\Scripts\python -m pip install -e ".[dev]"
  pause
  exit /b 1
)

rem A distinct random DB keeps this human test independent from ordinary local demo uploads.
set "DOCUMENTS_DB_PATH=%CD%\data\phase13-%RANDOM%-%RANDOM%.db"
set "ARTIFACTS_DIR=%CD%\artifacts\phase13"

echo Phase 13 Screen Reader Test: http://127.0.0.1:8001
echo Fresh isolated database: %DOCUMENTS_DB_PATH%
echo Upload DEMO-0002.txt, then DEMO-0001.txt exactly once. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 8001
pause
