import asyncio
import logging
import time
from urllib.parse import urlparse

import aiohttp

from config import get_auth_servers

logger = logging.getLogger(__name__)

_connector: aiohttp.TCPConnector | None = None
_session: aiohttp.ClientSession | None = None
_loop: asyncio.AbstractEventLoop | None = None

_profile_cache: dict[str, tuple[float, dict]] = {}
PROFILE_CACHE_TTL = 300  # 5 minutes


def _get_session() -> aiohttp.ClientSession:
    global _session, _connector, _loop
    current_loop = asyncio.get_running_loop()
    if _session is None or _session.closed or _loop is not current_loop:
        if _session and not _session.closed:
            asyncio.ensure_future(_session.close())
        if _connector:
            asyncio.ensure_future(_connector.close())
        _connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=5,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        _session = aiohttp.ClientSession(
            connector=_connector,
            timeout=aiohttp.ClientTimeout(total=30),
        )
        _loop = current_loop
    return _session


async def close_session() -> None:
    global _session, _connector
    if _session and not _session.closed:
        await _session.close()
        _session = None
    if _connector:
        await _connector.close()
        _connector = None


def _split_session_url(session_url: str) -> tuple[str, str]:
    idx = session_url.find("/sessionserver/")
    if idx != -1:
        return session_url[:idx], session_url[idx:]
    parsed = urlparse(session_url)
    path = parsed.path
    if "/session/" in path:
        return f"{parsed.scheme}://{parsed.netloc}", path
    return session_url, "/sessionserver/session/minecraft/hasJoined"


def _derive_auth_base_url(session_url: str) -> str:
    base, _ = _split_session_url(session_url)
    if "sessionserver." in base:
        return base.replace("sessionserver.", "authserver.")
    return base + "/authserver"


def _derive_session_base_url(session_url: str) -> str:
    base, path = _split_session_url(session_url)
    if "/sessionserver/" in path:
        return base + "/sessionserver/session"
    return base + "/session"


def _get_enabled_servers() -> list:
    return [s for s in get_auth_servers() if s.get("enabled", True)]


def _get_cached_profile(cache_key: str) -> dict | None:
    entry = _profile_cache.get(cache_key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > PROFILE_CACHE_TTL:
        del _profile_cache[cache_key]
        return None
    return data


def _set_cached_profile(cache_key: str, data: dict) -> None:
    _profile_cache[cache_key] = (time.time(), data)


async def _request(
    method: str,
    url: str,
    timeout: int = 10000,
    json_data: dict | None = None,
    params: dict | None = None,
) -> dict | list | None:
    session = _get_session()
    t = aiohttp.ClientTimeout(total=timeout / 1000)
    try:
        async with session.request(method, url, json=json_data, params=params, timeout=t) as resp:
            if resp.status == 200:
                text = await resp.text()
                if not text.strip():
                    return None
                return await resp.json(content_type=None)
            elif resp.status == 204:
                return {}
            else:
                logger.debug(f"Upstream {url} returned {resp.status}")
                return None
    except Exception as e:
        logger.debug(f"Upstream {url} error: {e}")
        return None


async def auth_action(server: dict, action: str, payload: dict) -> dict | None:
    auth_base = _derive_auth_base_url(server["url"])
    url = f"{auth_base}/{action}"
    timeout = server.get("timeout", 10000)
    return await _request("POST", url, timeout=timeout, json_data=payload)


async def try_authenticate_all(payload: dict) -> tuple[dict | None, str | None]:
    servers = _get_enabled_servers()
    if not servers:
        return None, None

    async def try_one(server: dict) -> tuple[dict | None, str | None]:
        result = await auth_action(server, "authenticate", payload)
        if result and "accessToken" in result:
            return result, server["id"]
        return None, None

    tasks = [try_one(s) for s in servers]
    for coro in asyncio.as_completed(tasks):
        result, sid = await coro
        if result is not None:
            return result, sid

    return None, None


async def join_for_server(server: dict, payload: dict) -> bool:
    session_base = _derive_session_base_url(server["url"])
    url = f"{session_base}/minecraft/join"
    timeout = server.get("timeout", 10000)
    session = _get_session()
    t = aiohttp.ClientTimeout(total=timeout / 1000)
    try:
        async with session.post(url, json=payload, timeout=t) as resp:
            return resp.status == 204 or resp.status == 200
    except Exception as e:
        logger.debug(f"Join upstream {url} error: {e}")
        return False


async def hasjoined_for_server(server: dict, params: dict) -> dict | None:
    url = server["url"]
    timeout = server.get("timeout", 10000)
    return await _request("GET", url, timeout=timeout, params=params)


async def profile_for_server(server: dict, uuid: str) -> dict | None:
    cache_key = f"{server['id']}:{uuid}"
    cached = _get_cached_profile(cache_key)
    if cached is not None:
        return cached

    session_base = _derive_session_base_url(server["url"])
    url = f"{session_base}/minecraft/profile/{uuid}"
    timeout = server.get("timeout", 10000)
    result = await _request("GET", url, timeout=timeout)
    if result and "id" in result:
        _set_cached_profile(cache_key, result)
    return result


async def profile_for_uuid(uuid: str) -> dict | None:
    servers = _get_enabled_servers()
    if not servers:
        return None

    async def try_one(server: dict) -> dict | None:
        return await profile_for_server(server, uuid)

    tasks = [try_one(s) for s in servers]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result and "id" in result:
            return result

    return None


async def check_server_status(server: dict) -> dict:
    url = server["url"]
    timeout_ms = server.get("timeout", 10000)
    timeout = min(timeout_ms, 5000)
    result = {
        "name": server.get("name", ""),
        "url": url,
        "online": False,
        "latency_ms": None,
        "error": None,
    }
    try:
        start = time.monotonic()
        t = aiohttp.ClientTimeout(total=timeout / 1000)
        session = _get_session()
        async with session.get(url, timeout=t) as resp:
            elapsed = (time.monotonic() - start) * 1000
            result["latency_ms"] = round(elapsed)
            result["online"] = True
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
    except aiohttp.ClientError as e:
        result["error"] = str(e)[:80]
    except Exception as e:
        result["error"] = str(e)[:80]
    return result
