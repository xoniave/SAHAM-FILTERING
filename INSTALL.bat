@echo off
cd /d %~dp0
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
if not exist app\data\history mkdir app\data\history
echo.
echo ============================================================
echo Installation complete.
echo ============================================================
echo NEXT STEP:
echo   1. Run SYNC_REAL_DATA.bat once to fetch the current IDX universe
echo      and cache real daily OHLCV.
echo   2. Then run RUN.bat.
echo.
pause
