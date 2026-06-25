@echo off
chcp 65001 >nul
echo ==========================================
echo   AI-CAD-Audit-System v7.0
echo ==========================================
echo.

cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set V7_ADMIN_PORT=2708
set "PYTHONPATH=%~dp0src"
set "V7_INPUT_DIR=%~dp0src\v7\input"
set "V7_OUTPUT_DIR=%~dp0src\v7\output_v7.0"

echo [OK] Starting server...
echo [OK] Opening browser in 3 seconds...
echo [OK] URL: http://localhost:2708
echo.

start "" cmd /c "ping -n 4 127.0.0.1 >nul && start http://localhost:2708"

.venv\Scripts\python.exe -m v7.admin.server

echo.
echo Server stopped. Press any key to exit...
pause >nul
