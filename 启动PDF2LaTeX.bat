@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM Always run from the project directory, regardless of where this file is launched.
cd /d "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

REM Create the project-local virtual environment on first launch.
if not exist "%VENV_PY%" (
    echo [1/3] 正在创建项目虚拟环境 .venv ...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo 未找到 Python。请先安装 Python 3.10 或更高版本，并勾选“Add Python to PATH”。
            pause
            exit /b 1
        )
        python -m venv .venv
    )
    if errorlevel 1 (
        echo 创建虚拟环境失败。
        pause
        exit /b 1
    )
)

REM Do not use Anaconda's Python: verify that the project environment has the runtime dependencies.
"%VENV_PY%" -c "import flask, flask_socketio, pdfplumber, cv2, pytesseract, dotenv" >nul 2>nul
if errorlevel 1 (
    echo [2/3] 首次启动：正在安装项目依赖，请稍候...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo 依赖安装失败。请检查网络连接后重试。
        pause
        exit /b 1
    )
) else (
    echo [2/3] 项目依赖已就绪。
)

echo [3/3] 正在启动 PDF2LaTeX ...
echo.
echo 浏览器访问地址: http://127.0.0.1:5000
echo 按 Ctrl+C 可停止服务。
echo.
"%VENV_PY%" backend\app_enhanced.py

echo.
echo 服务已停止。
pause
