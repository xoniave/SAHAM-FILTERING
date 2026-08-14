@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run INSTALL.bat first.
  pause
  exit /b 1
)
echo.
echo ============================================================
echo  FIX YFINANCE REPAIR DEPENDENCY - SCIPY
echo ============================================================
.venv\Scripts\python.exe -m pip install --upgrade "scipy>=1.14.1,<2" "yfinance[repair]>=0.2.60,<1"
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  pause
  exit /b 1
)
echo.
.venv\Scripts\python.exe -c "import scipy, yfinance; print('SciPy', scipy.__version__, '| yfinance', yfinance.__version__, '| OK')"
echo.
echo FIX COMPLETE.
echo Now run SYNC_REAL_DATA.bat again.
pause
