@echo off

echo ========================================
echo   Excel Assistant - Windows Build
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found, please install Python 3.10+
    pause
    exit /b 1
)

:: Create venv
if not exist venv (
    echo [1/4] Creating venv...
    python -m venv venv
)

:: Activate and install
echo [2/4] Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller -q

:: Build
echo [3/4] Building (2-3 minutes)...
pyinstaller excel_assistant.spec --noconfirm

:: Create inputs/outputs in dist
echo [4/4] Creating directories...
if not exist "dist\ExcelAssistant\inputs" mkdir "dist\ExcelAssistant\inputs"
if not exist "dist\ExcelAssistant\outputs" mkdir "dist\ExcelAssistant\outputs"

echo.
echo ========================================
echo   Build complete!
echo   Output: dist\ExcelAssistant\
echo   Run: ExcelAssistant.exe
echo ========================================
pause
