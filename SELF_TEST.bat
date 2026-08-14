@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run INSTALL.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate
set PYTHONPATH=%CD%
set MARKET_PROVIDER=demo
python tools\smoke_test.py
pause
