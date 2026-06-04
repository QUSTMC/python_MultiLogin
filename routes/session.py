import asyncio
import logging
from flask import Blueprint, request, jsonify

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
    props = profile.get("properties", [])
    return any(p.get("name") == "textures" for p in props)


def _enrich_with_skin(profile: dict, server: dict) -> dict:
    if _has_skin_properties(profile):
        return profile
    uuid = profile.get("id", "")
    if not uuid:
        return profile
    skin = asyncio.run(upstream.profile_for_server(server, uuid))
    if skin and _has_skin_properties(skin):
        profile["properties"] = skin["properties"]
        logger.info(f"Enriched: uuid={uuid[:12]}...")
    return profile


def _apply_skin_restorer(profile: dict) -> dict:
    from config import get_config
    cfg = get_config()
    restorer_mode = cfg.get("skin_restorer", "off").lower()

    if restorer_mode == "off":
        return profile

    props = profile.get("properties", [])
    if not any(p.get("name") == "textures" for p in props):
        return profile

    method = cfg.get("skin_restorer_method", "url").lower()
    profile["properties"] = skin_restorer.restore_skin(props, method)
    return profile


def _check_name_binding(username: str, uuid: str) -> str | None:
    from config import get_config
    cfg = get_config()
    if cfg.get("allow_duplicate_names", False):
        return None

    binding = database.get_name_binding(username)
    if binding is None:
        return None

    if binding["uuid"] != uuid:
        return f"该用户名已被其他账号绑定"
    return None


def _check_ban(username: str, uuid: str) -> str | None:
    ban = database.is_banned(username, uuid)
    if ban:
        reason = ban.get("reason", "")
        if reason:
            return f"你已被封禁: {reason}"
        return "你已被封禁"
    return None


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
            ok = asyncio.run(upstream.join_for_server(server, payload))
            if ok:
                _join_cache[server_id] = {"service_id": service_id, "username": username}
                logger.info(f"Join: {username} -> {server['name']} serverId={server_id[:12]}...")
                return jsonify({}), 204

    from config import get_auth_servers
    servers = [s for s in get_auth_servers() if s.get("enabled")]
    sorted_servers = sorted(servers, key=lambda s: s.get("priority", 999))
    for server in sorted_servers:
        ok = asyncio.run(upstream.join_for_server(server, payload))
        if ok:
            sid = server["id"]
            _join_cache[server_id] = {"service_id": sid, "username": username}
            if username:
                database.set_player_service(username, sid)
            logger.info(f"Join (fallback): {username} -> {server['name']} serverId={server_id[:12]}...")
            return jsonify({}), 204

    logger.warning(f"Join failed: serverId={server_id[:12]}...")
    return jsonify({
        "error": "ForbiddenOperationException",
        "errorMessage": "Invalid token.",
    }), 403


@session_bp.route("/sessionserver/session/minecraft/hasJoined", methods=["GET"])
def has_joined():
    username = request.args.get("username", "")
    server_id = request.args.get("serverId", "")
    ip = request.args.get("ip", "")

    cached = _join_cache.pop(server_id, None)

    if cached:
        service_id = cached["service_id"]
        server = _get_server_by_id(service_id)
        if server:
            params = {"username": username, "serverId": server_id}
            if server.get("track_ip", True) and ip:
                params["ip"] = ip
            result = asyncio.run(upstream.hasjoined_for_server(server, params))
            if result and "id" in result:
                dup_error = _check_name_binding(username, result["id"])
                if dup_error:
                    logger.warning(f"HasJoined blocked: {dup_error} (username={username}, uuid={result['id'][:12]}...)")
                    return jsonify({"error": "ForbiddenOperationException", "errorMessage": dup_error}), 403

                ban_error = _check_ban(username, result["id"])
                if ban_error:
                    logger.warning(f"HasJoined blocked: banned (username={username}, uuid={result['id'][:12]}...)")
                    return jsonify({"error": "ForbiddenOperationException", "errorMessage": ban_error}), 403

                database.set_name_binding(username, result["id"], service_id)
                _record_uuid_mapping(result["id"], service_id, username)
                result = _enrich_with_skin(result, server)
                result = _apply_skin_restorer(result)
                logger.info(f"HasJoined: {username} via {server['name']}")
                return jsonify(result)

    from config import get_auth_servers
    servers = [s for s in get_auth_servers() if s.get("enabled")]
    sorted_servers = sorted(servers, key=lambda s: s.get("priority", 999))
    for server in sorted_servers:
        params = {"username": username, "serverId": server_id}
        if server.get("track_ip", True) and ip:
            params["ip"] = ip
        result = asyncio.run(upstream.hasjoined_for_server(server, params))
        if result and "id" in result:
            sid = server["id"]
            dup_error = _check_name_binding(username, result["id"])
            if dup_error:
                logger.warning(f"HasJoined blocked (fallback): {dup_error} (username={username}, uuid={result['id'][:12]}...)")
                return jsonify({"error": "ForbiddenOperationException", "errorMessage": dup_error}), 403

            ban_error = _check_ban(username, result["id"])
            if ban_error:
                logger.warning(f"HasJoined blocked (fallback): banned (username={username}, uuid={result['id'][:12]}...)")
                return jsonify({"error": "ForbiddenOperationException", "errorMessage": ban_error}), 403

            database.set_name_binding(username, result["id"], sid)
            _record_uuid_mapping(result["id"], sid, username)
            result = _enrich_with_skin(result, server)
            result = _apply_skin_restorer(result)
            logger.info(f"HasJoined (fallback): {username} via {server['name']}")
            return jsonify(result)

    logger.warning(f"HasJoined failed: {username}")
    return jsonify({
        "error": "ForbiddenOperationException",
        "errorMessage": "Invalid token.",
    }), 403


@session_bp.route("/sessionserver/session/minecraft/profile/<uuid>", methods=["GET"])
def profile(uuid: str):
    service_id = database.get_service_by_uuid(uuid)

    if service_id is not None:
        server = _get_server_by_id(service_id)
        if server:
            result = asyncio.run(upstream.profile_for_server(server, uuid))
            if result:
                result = _apply_skin_restorer(result)
                return jsonify(result)

    result = asyncio.run(upstream.profile_for_uuid(uuid))
    if result:
        result = _apply_skin_restorer(result)
        return jsonify(result)

    return jsonify({}), 204
