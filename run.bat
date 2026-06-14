@echo off
chcp 65001 >nul

if not exist venv (
    echo 创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo 安装依赖...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

python app.py
