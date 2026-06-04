import hashlib
import logging
import base64
import json

import aiohttp

import async_utils
import database

logger = logging.getLogger(__name__)

MINESKIN_URL_API = "https://api.mineskin.org/generate/url"
MINESKIN_UPLOAD_API = "https://api.mineskin.org/generate/upload"
TRUSTED_DOMAINS = (".minecraft.net", ".mojang.com")


def _is_trusted_url(url: str) -> bool:
    return any(domain in url for domain in TRUSTED_DOMAINS)


def _extract_skin_info(properties: list) -> tuple[str | None, str, str]:
    for prop in properties:
        if prop.get("name") == "textures":
            try:
                decoded = json.loads(base64.b64decode(prop["value"]))
                skin = decoded.get("textures", {}).get("SKIN", {})
                url = skin.get("url")
                model = "slim" if skin.get("metadata", {}).get("model") == "slim" else "classic"
                return url, model, prop.get("value", "")
            except Exception:
                pass
    return None, "classic", ""


def _build_restored_property(value: str, signature: str) -> dict:
    return {"name": "textures", "value": value, "signature": signature}


async def _download_skin(url: str) -> bytes | None:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) > 100:
                        return data
                logger.debug(f"Skin download {resp.status}: {url[:80]}")
    except Exception as e:
        logger.debug(f"Skin download error: {e}")
    return None


async def _call_mineskin_url(skin_url: str, model: str) -> dict | None:
    payload = {
        "url": skin_url,
        "variant": model,
        "name": "multilogin",
        "visibility": 0,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": "MultiLogin-Python/1.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(MINESKIN_URL_API, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    texture = data.get("data", {}).get("texture", {})
                    if texture.get("value") and texture.get("signature"):
                        return texture
                text = await resp.text()
                logger.warning(f"MineSkin URL failed: {resp.status} {text[:200]}")
    except Exception as e:
        logger.warning(f"MineSkin URL error: {e}")
    return None


async def _call_mineskin_upload(skin_bytes: bytes, model: str) -> dict | None:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": "MultiLogin-Python/1.0"}
        form = aiohttp.FormData()
        form.add_field("file", skin_bytes, filename="skin.png", content_type="image/png")
        form.add_field("variant", model)
        form.add_field("name", "multilogin")
        form.add_field("visibility", "0")
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(MINESKIN_UPLOAD_API, data=form) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    texture = data.get("data", {}).get("texture", {})
                    if texture.get("value") and texture.get("signature"):
                        return texture
                text = await resp.text()
                logger.warning(f"MineSkin upload failed: {resp.status} {text[:200]}")
    except Exception as e:
        logger.warning(f"MineSkin upload error: {e}")
    return None


def _get_cache_key(skin_url: str, model: str) -> str:
    url_hash = hashlib.sha256(skin_url.encode()).hexdigest()
    return f"{url_hash}_{model}"


def restore_skin(properties: list, method: str = "url") -> list:
    skin_url, model, original_value = _extract_skin_info(properties)

    if not skin_url:
        return properties

    if _is_trusted_url(skin_url):
        return properties

    cache_key = _get_cache_key(skin_url, model)
    cached = database.get_skin_cache(cache_key)
    if cached:
        new_prop = _build_restored_property(cached["value"], cached["signature"])
        return [new_prop if p.get("name") == "textures" else p for p in properties]

    if method == "upload":
        skin_bytes = async_utils.run_async(_download_skin(skin_url))
        if skin_bytes:
            texture = async_utils.run_async(_call_mineskin_upload(skin_bytes, model))
        else:
            logger.warning(f"Failed to download skin for upload: {skin_url[:60]}")
            return properties
    else:
        texture = async_utils.run_async(_call_mineskin_url(skin_url, model))
        if not texture:
            skin_bytes = async_utils.run_async(_download_skin(skin_url))
            if skin_bytes:
                logger.info(f"URL method failed, trying upload fallback...")
                texture = async_utils.run_async(_call_mineskin_upload(skin_bytes, model))

    if texture:
        database.set_skin_cache(cache_key, texture["value"], texture["signature"])
        logger.info(f"Skin restored: {skin_url[:60]}...")
        new_prop = _build_restored_property(texture["value"], texture["signature"])
        return [new_prop if p.get("name") == "textures" else p for p in properties]

    logger.warning(f"Skin restore failed: {skin_url[:60]}")
    return properties
