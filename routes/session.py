import logging
from flask import Blueprint, request, jsonify

import async_utils
import upstream
import database
import skin_restorer
import session_store

logger = logging.getLogger(__name__)

session_bp = Blueprint("session", __name__)

_join_cache: dict = {}


def _get_server_by_id(service_id: str):
    from config import get_server_by_id
    return get_server_by_id(service_id)


def _record_uuid_mapping(uuid: str, service_id: str, username: str | None = None):
    database.set_uuid_service(uuid, service_id, username)


def _has_skin_properties(profile: dict) -> bool:
    return any(p.get("name") == "textures" for p in profile.get("properties", []))


def _enrich_with_skin(profile: dict, server: dict) -> dict:
    if _has_skin_properties(profile):
        return profile
    uuid = profile.get("id", "")
    if not uuid:
        return profile
    skin = async_utils.run_async(upstream.profile_for_server(server, uuid))
    if skin and _has_skin_properties(skin):
        profile["properties"] = skin["properties"]
    return profile


def _apply_skin_restorer(profile: dict) -> dict:
    from config import get_config
    cfg = get_config()
    if cfg.get("skin_restorer", "off").lower() == "off":
        return profile
    if not _has_skin_properties(profile):
        return profile
    method = cfg.get("skin_restorer_method", "url").lower()
    profile["properties"] = skin_restorer.restore_skin(profile["properties"], method)
    return profile


def _check_name_binding(username: str, uuid: str) -> str | None:
    from config import get_config
    if get_config().get("allow_duplicate_names", False):
        return None
    binding = database.get_name_binding(username)
    if binding and binding["uuid"] != uuid:
        return "该用户名已被其他账号绑定"
    return None


def _check_ban(username: str, uuid: str) -> str | None:
    ban = database.is_banned(username, uuid)
    if ban:
        reason = ban.get("reason", "")
        return f"你已被封禁: {reason}" if reason else "你已被封禁"
    return None


def _process_hasjoined(username: str, server: dict, params: dict) -> dict | None:
    result = async_utils.run_async(upstream.hasjoined_for_server(server, params))
    if not result or "id" not in result:
        return None

    uuid = result["id"]
    service_id = server["id"]

    error = _check_name_binding(username, uuid)
    if error:
        return {"error": error, "code": 403}

    error = _check_ban(username, uuid)
    if error:
        return {"error": error, "code": 403}

    database.set_name_binding(username, uuid, service_id)
    _record_uuid_mapping(uuid, service_id, username)
    result = _enrich_with_skin(result, server)
    result = _apply_skin_restorer(result)
    return result


@session_bp.route("/sessionserver/session/minecraft/join", methods=["POST"])
def join():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid request"}), 400

    access_token = payload.get("accessToken", "")
    server_id = payload.get("selectedServer", "") or payload.get("serverId", "")
    username = ""

    match = session_store.get_by_token(access_token)
    if match:
        username, service_id = match
        server = _get_server_by_id(service_id)
        if server:
            ok = async_utils.run_async(upstream.join_for_server(server, payload))
            if ok:
                _join_cache[server_id] = {"service_id": service_id, "username": username}
                logger.info(f"Join: {username} -> {server['name']} serverId={server_id[:12]}...")
                return jsonify({}), 204

    from config import get_auth_servers
    servers = sorted([s for s in get_auth_servers() if s.get("enabled")], key=lambda s: s.get("priority", 999))
    for server in servers:
        ok = async_utils.run_async(upstream.join_for_server(server, payload))
        if ok:
            sid = server["id"]
            _join_cache[server_id] = {"service_id": sid, "username": username}
            if username:
                database.set_player_service(username, sid)
            logger.info(f"Join (fallback): {username} -> {server['name']} serverId={server_id[:12]}...")
            return jsonify({}), 204

    logger.warning(f"Join failed: serverId={server_id[:12]}...")
    return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid token."}), 403


@session_bp.route("/sessionserver/session/minecraft/hasJoined", methods=["GET"])
def has_joined():
    username = request.args.get("username", "")
    server_id = request.args.get("serverId", "")
    ip = request.args.get("ip", "")

    cached = _join_cache.pop(server_id, None)

    if cached:
        server = _get_server_by_id(cached["service_id"])
        if server:
            params = {"username": username, "serverId": server_id}
            if server.get("track_ip", True) and ip:
                params["ip"] = ip
            result = _process_hasjoined(username, server, params)
            if result:
                if "error" in result:
                    logger.warning(f"HasJoined blocked: {result['error']} (username={username})")
                    return jsonify({"error": "ForbiddenOperationException", "errorMessage": result["error"]}), result["code"]
                logger.info(f"HasJoined: {username} via {server['name']}")
                return jsonify(result)

    from config import get_auth_servers
    servers = sorted([s for s in get_auth_servers() if s.get("enabled")], key=lambda s: s.get("priority", 999))
    for server in servers:
        params = {"username": username, "serverId": server_id}
        if server.get("track_ip", True) and ip:
            params["ip"] = ip
        result = _process_hasjoined(username, server, params)
        if result:
            if "error" in result:
                logger.warning(f"HasJoined blocked (fallback): {result['error']} (username={username})")
                return jsonify({"error": "ForbiddenOperationException", "errorMessage": result["error"]}), result["code"]
            logger.info(f"HasJoined (fallback): {username} via {server['name']}")
            return jsonify(result)

    logger.warning(f"HasJoined failed: {username}")
    return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid token."}), 403


@session_bp.route("/sessionserver/session/minecraft/profile/<uuid>", methods=["GET"])
def profile(uuid: str):
    service_id = database.get_service_by_uuid(uuid)
    if service_id is not None:
        server = _get_server_by_id(service_id)
        if server:
            result = async_utils.run_async(upstream.profile_for_server(server, uuid))
            if result:
                return jsonify(_apply_skin_restorer(result))

    result = async_utils.run_async(upstream.profile_for_uuid(uuid))
    if result:
        return jsonify(_apply_skin_restorer(result))

    return jsonify({}), 204
