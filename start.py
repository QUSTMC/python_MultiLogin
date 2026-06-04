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

def has_waitress():
    try:
        import waitress
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

    if has_waitress():
        print("[+] Using waitress (production mode)", flush=True)
        from app import create_app
        from waitress import serve
        from auth_key import load_or_create_key
        import config
        import database

        cfg = config.load_config()
        server_cfg = cfg.get("server", {})
        key = server_cfg.get("access_key")
        if not key:
            key = load_or_create_key()
            server_cfg["access_key"] = key
            config.save_config()

        port = server_cfg.get("port", 8080)
        database.init_db()

        print("=" * 60, flush=True)
        print(f"  Access Key: {key}", flush=True)
        print(f"  Admin URL:  http://localhost:{port}/admin/", flush=True)
        print("=" * 60, flush=True)

        app = create_app()
        serve(app, host="0.0.0.0", port=port, threads=4)
    else:
        print("[!] waitress not found, using Flask dev server", flush=True)
        subprocess.run([sys.executable, "app.py"])

if __name__ == "__main__":
    main()
