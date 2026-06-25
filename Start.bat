@echo off
chcp 65001 >nul 2>&1
title AI智能审图系统 v7.0

echo.
echo ========================================
echo   AI智能审图系统 v7.0
echo ========================================
echo.

cd /d "%~dp0"

REM ==== 查找 Python ====
set PYTHON_EXE=
for %%P in (python python3 py) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%V in ('%%P --version 2^>nul') do (
            echo %%V | findstr "3\.1[0-9]" >nul
            if not errorlevel 1 set PYTHON_EXE=%%P
        )
    )
)

if defined PYTHON_EXE goto :HAS_PYTHON

for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "C:\Python311"
    "C:\Python312"
) do (
    if exist "%%~D\python.exe" (
        set PYTHON_EXE=%%~D\python.exe
        goto :HAS_PYTHON
    )
)

echo [FAIL] 未找到 Python 3.10+
echo 请先安装: https://www.python.org/downloads/windows/
echo 安装时勾选 "Add Python to PATH"
pause
exit /b 1

:HAS_PYTHON
echo [OK] Python: %PYTHON_EXE%
echo.

REM ==== 创建虚拟环境 ====
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] 首次运行，创建虚拟环境...
    "%PYTHON_EXE%" -m venv .venv
    if errorlevel 1 (
        echo [FAIL] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
    echo.
)

set VENV=.venv\Scripts\python.exe

REM ==== 安装依赖 ====
"%VENV%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 首次运行，安装依赖 ^(约5-10分钟^)...
    "%VENV%" -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    "%VENV%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [WARN] 清华源失败, 尝试默认源...
        "%VENV%" -m pip install -r requirements.txt
    )
    echo [OK] 依赖安装完成
    echo.
)

REM ==== 复制 .env ====
if not exist ".env" (
    if exist ".env.template" copy /y .env.template .env >nul
)

REM ==== 设置环境 ====
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set V7_ADMIN_PORT=2708
set "PYTHONPATH=%~dp0src"

REM ==== 启动 ====
echo [OK] 启动服务 http://localhost:2708
echo.
start http://localhost:2708
"%VENV%" -m v7.admin.server

pause
