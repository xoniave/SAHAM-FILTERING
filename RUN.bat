@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run INSTALL.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate
set PYTHONPATH=%CD%
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
