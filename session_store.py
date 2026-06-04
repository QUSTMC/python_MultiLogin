import logging

logger = logging.getLogger(__name__)

_cache: dict[str, dict] = {}


def record_auth(username: str, service_id: str, access_token: str, client_token: str | None = None) -> None:
    _cache[username.lower()] = {
        "service_id": service_id,
        "access_token": access_token,
        "client_token": client_token,
    }


def get_by_token(access_token: str) -> tuple[str, str] | None:
    for uname, data in _cache.items():
        if data.get("access_token") == access_token:
            return uname, data["service_id"]
    return None


def get_by_username(username: str) -> dict | None:
    return _cache.get(username.lower())


def update(username: str, access_token: str, client_token: str | None = None) -> None:
    key = username.lower()
    if key in _cache:
        _cache[key]["access_token"] = access_token
        _cache[key]["client_token"] = client_token
    else:
        record_auth(username, "", access_token, client_token)


def remove(username: str) -> dict | None:
    return _cache.pop(username.lower(), None)


def get_service_id_for_server(server_id: str) -> str | None:
    for data in _cache.values():
        if data.get("service_id") == server_id:
            return data["service_id"]
    return None
