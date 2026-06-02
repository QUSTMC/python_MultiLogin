import os
import threading
from ruamel.yaml import YAML

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yml")

_yaml = YAML()
_yaml.preserve_quotes = True

_config: dict = {}
_lock = threading.Lock()

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "access_key": "",
    },
    "skin_restorer": "off",
    "skin_restorer_method": "url",
    "auth_servers": [
        {
            "name": "LittleSkin",
            "url": "https://littleskin.cn/api/yggdrasil/sessionserver/session/minecraft/hasJoined",
            "priority": 1,
            "enabled": True,
            "timeout": 10000,
            "track_ip": True,
            "init_uuid": "online",
        },
        {
            "name": "Mojang Official",
            "url": "https://sessionserver.mojang.com/session/minecraft/hasJoined",
            "priority": 2,
            "enabled": True,
            "timeout": 10000,
            "track_ip": True,
            "init_uuid": "online",
        },
    ],
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _write_config() -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        _yaml.dump(_config, f)


def load_config() -> dict:
    global _config
    with _lock:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _config = _yaml.load(f) or {}
            _config = _deep_merge(DEFAULT_CONFIG, _config)
        else:
            _config = DEFAULT_CONFIG.copy()
            _write_config()
    return _config


def get_config() -> dict:
    return _config


def save_config() -> None:
    with _lock:
        _write_config()


def update_config(new_config: dict) -> None:
    global _config
    with _lock:
        _config = new_config
        _write_config()


def get_auth_servers() -> list:
    return _config.get("auth_servers", [])


def get_server_setting() -> dict:
    return _config.get("server", {})


def update_auth_servers(servers: list) -> None:
    with _lock:
        _config["auth_servers"] = servers
        _write_config()
