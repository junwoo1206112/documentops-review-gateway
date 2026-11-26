@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [.venv not found] Run: python -m venv .venv ^&^& .venv\Scripts\python -m pip install -e ".[dev]"
  pause
  exit /b 1
)

echo DocumentOps Review Gateway: http://127.0.0.1:8000
echo Keep this window open while using the site. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 8000
pause
