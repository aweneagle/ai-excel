@echo off
chcp 65001 >nul
echo ========================================
echo   Excel 智能助手 - Windows 打包脚本
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: Create venv
if not exist venv (
    echo [1/4] 创建虚拟环境...
    python -m venv venv
)

:: Activate and install
echo [2/4] 安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller -q

:: Build
echo [3/4] 打包中（约2-3分钟）...
pyinstaller excel_assistant.spec --noconfirm

:: Create inputs/outputs in dist
echo [4/4] 创建目录结构...
if not exist "dist\Excel智能助手\inputs" mkdir "dist\Excel智能助手\inputs"
if not exist "dist\Excel智能助手\outputs" mkdir "dist\Excel智能助手\outputs"

echo.
echo ========================================
echo   打包完成！
echo   输出目录: dist\Excel智能助手\
echo   双击 Excel智能助手.exe 启动
echo ========================================
pause
