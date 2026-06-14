@echo off

if not exist venv (
    echo Creating venv...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

python app.py
if errorlevel 1 (
    echo.
    echo Failed to start, check the error above.
    pause
)
