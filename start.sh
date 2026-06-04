#!/bin/bash
cd "$(dirname "$0")"

echo "[*] Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "[!] Python3 not found. Please install Python 3.10+."
    exit 1
fi

echo "[*] Checking dependencies..."
if ! python3 -c "import flask, aiohttp, yaml, ruamel.yaml" &>/dev/null; then
    echo "[*] Installing dependencies..."
    python3 -m pip install -r requirements.txt -q
    if [ $? -ne 0 ]; then
        echo "[!] Failed to install dependencies."
        exit 1
    fi
    echo "[+] Dependencies installed."
else
    echo "[+] Dependencies OK."
fi

echo "[*] Starting MultiLogin Python..."
if python3 -c "import gunicorn" &>/dev/null; then
    echo "[+] Using gunicorn (production mode)"
    python3 -m gunicorn -c gunicorn.conf.py "app:create_app()"
elif python3 -c "import waitress" &>/dev/null; then
    echo "[+] Using waitress (production mode)"
    python3 -c "from app import create_app; from waitress import serve; app = create_app(); serve(app, host='0.0.0.0', port=8080, threads=4)"
else
    echo "[!] No production server found, using Flask dev server"
    python3 app.py
fi
