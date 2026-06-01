@echo off
chcp 65001 >nul 2>&1
title MultiLogin Python

cd /d "%~dp0"

echo [*] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python not found. Please install Python 3.10+.
    pause
    exit /b 1
)

echo [*] Checking dependencies...
python -c "import flask, aiohttp, yaml, ruamel.yaml" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing dependencies...
    pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [!] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [+] Dependencies installed.
) else (
    echo [+] Dependencies OK.
)

echo [*] Starting MultiLogin Python...
python app.py
pause
