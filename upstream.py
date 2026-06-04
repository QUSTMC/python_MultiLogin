import asyncio
import logging
import time
from urllib.parse import urlparse

import aiohttp

from config import get_auth_servers

logger = logging.getLogger(__name__)


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


async def _request(
    method: str,
    url: str,
    timeout: int = 10000,
    json_data: dict | None = None,
    params: dict | None = None,
) -> dict | list | None:
    t = aiohttp.ClientTimeout(total=timeout / 1000)
    try:
        async with aiohttp.ClientSession(timeout=t) as session:
            async with session.request(method, url, json=json_data, params=params) as resp:
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
    t = aiohttp.ClientTimeout(total=timeout / 1000)
    try:
        async with aiohttp.ClientSession(timeout=t) as session:
            async with session.post(url, json=payload) as resp:
                return resp.status == 204 or resp.status == 200
    except Exception as e:
        logger.debug(f"Join upstream {url} error: {e}")
        return False


async def hasjoined_for_server(server: dict, params: dict) -> dict | None:
    url = server["url"]
    timeout = server.get("timeout", 10000)
    return await _request("GET", url, timeout=timeout, params=params)


async def profile_for_server(server: dict, uuid: str) -> dict | None:
    session_base = _derive_session_base_url(server["url"])
    url = f"{session_base}/minecraft/profile/{uuid}"
    timeout = server.get("timeout", 10000)
    return await _request("GET", url, timeout=timeout)


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
    timeout = aiohttp.ClientTimeout(total=min(timeout_ms, 5000) / 1000)
    result = {
        "name": server.get("name", ""),
        "url": url,
        "online": False,
        "latency_ms": None,
        "error": None,
    }
    try:
        start = time.monotonic()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
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
