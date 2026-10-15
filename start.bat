@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   ShortLink 短链服务
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 找不到虚拟环境 .venv
    echo.
    echo 请先在当前目录执行:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "app\main.py" (
    echo [错误] 找不到 app\main.py，请确认脚本放在项目根目录
    pause
    exit /b 1
)

echo 正在启动服务，请稍候...
echo.
echo   访问地址: http://127.0.0.1:8000
echo   接口文档: http://127.0.0.1:8000/docs
echo.
echo 关闭此窗口即停止服务
echo ----------------------------------------
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo 服务已停止。
pause
