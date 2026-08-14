@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run INSTALL.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate
set PYTHONPATH=%CD%
python -c "import scipy" >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: SciPy is missing. yfinance repair mode requires SciPy.
  echo Run FIX_SCIPY.bat, then run this sync again.
  echo.
  pause
  exit /b 1
)
echo.
echo ============================================================
echo  IDX Decision Dashboard - REAL EOD DATA SYNC
echo ============================================================
echo  Source universe/latest completed session: IDX website data
echo  Historical daily OHLCV: Yahoo Finance via yfinance
echo  This is REAL EOD data, NOT a licensed real-time feed.
echo ============================================================
echo.
python tools\sync_real_data.py
if errorlevel 1 (
  echo.
  echo Sync finished with errors. Read the messages above.
  pause
  exit /b 1
)
echo.
echo Real EOD sync complete.
echo Now run RUN.bat and open http://127.0.0.1:8765
echo.
pause
