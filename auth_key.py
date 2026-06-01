import secrets
import os

KEY_FILE = os.path.join(os.path.dirname(__file__), "data", ".access_key")


def generate_key() -> str:
    return secrets.token_urlsafe(32)


def load_or_create_key() -> str:
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            key = f.read().strip()
            if key:
                return key
    key = generate_key()
    with open(KEY_FILE, "w") as f:
        f.write(key)
    return key


def verify_key(provided_key: str, actual_key: str) -> bool:
    if not provided_key or not actual_key:
        return False
    return secrets.compare_digest(provided_key, actual_key)
