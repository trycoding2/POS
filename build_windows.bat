@echo off
setlocal
rem ============================================================
rem  Kirana Manager - one-shot Windows build script
rem  Paste into a terminal at the workspace root (the folder
rem  that contains backend\ and frontend\) and run:
rem      build_windows.bat
rem  Result: backend\dist\KiranaManager.exe  (single file)
rem  Requirements: Python 3.12+ and Node.js 18+ on PATH.
rem ============================================================

cd /d "%~dp0"

echo [1/5] Checking tools...
python --version >nul 2>&1 || (echo ERROR: Python not found. Install from python.org and tick "Add to PATH". & exit /b 1)
node --version >nul 2>&1 || (echo ERROR: Node.js not found. Install LTS from nodejs.org. & exit /b 1)

echo [2/5] Building frontend (React + TypeScript)...
pushd frontend
call npm install --no-audit --no-fund || (popd & echo ERROR: npm install failed. & exit /b 1)
call npm run build || (popd & echo ERROR: Frontend build failed. & exit /b 1)
popd

echo [3/5] Copying built frontend into backend...
if exist backend\dist\frontend rmdir /s /q backend\dist\frontend
xcopy /e /i /y frontend\dist backend\dist\frontend >nul || (echo ERROR: copy failed. & exit /b 1)

echo [4/5] Setting up Python environment...
pushd backend
if not exist venv python -m venv venv || (popd & echo ERROR: could not create venv. & exit /b 1)
call venv\Scripts\activate.bat || (popd & echo ERROR: could not activate venv. & exit /b 1)
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt pyinstaller --no-input --quiet || (popd & echo ERROR: pip install failed. & exit /b 1)

echo [5/5] Building single-file EXE (this takes a few minutes)...
pyinstaller kirana_manager.spec --noconfirm --clean || (popd & echo ERROR: PyInstaller build failed. & exit /b 1)
popd

echo.
echo ============================================================
echo  DONE! Your app is here:
echo    %~dp0backend\dist\KiranaManager.exe
echo.
echo  Double-click it (or run from a terminal). It starts the
echo  local server and opens http://127.0.0.1:8000 in your
echo  browser automatically. All shop data is saved in a
echo  "data" folder next to the EXE - back that folder up.
echo ============================================================
pause
