#!/usr/bin/env python3
"""MultiLogin Python - One-click launcher"""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def check_deps():
    try:
        import flask, aiohttp, yaml, ruamel.yaml
        return True
    except ImportError:
        return False

def main():
    print("[*] Checking Python...", flush=True)

    if not check_deps():
        print("[*] Installing dependencies...", flush=True)
        ret = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
        if ret.returncode != 0:
            print("[!] Failed to install dependencies.")
            sys.exit(1)
        print("[+] Dependencies installed.", flush=True)
    else:
        print("[+] Dependencies OK.", flush=True)

    print("[*] Starting MultiLogin Python...", flush=True)
    subprocess.run([sys.executable, "app.py"])

if __name__ == "__main__":
    main()
