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
python3 app.py
