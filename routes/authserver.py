import asyncio
import logging
from flask import Blueprint, request, jsonify

import upstream
import database

logger = logging.getLogger(__name__)

authserver_bp = Blueprint("authserver", __name__)

# In-memory session cache: username -> {service_id, access_token, client_token}
_session_cache: dict = {}


@authserver_bp.route("/authserver/authenticate", methods=["POST"])
def authenticate():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid request"}), 400

    username = payload.get("username", "")
    result, service_id = asyncio.run(upstream.try_authenticate_all(payload))

    if result is None:
        return jsonify({
            "error": "ForbiddenOperationException",
            "errorMessage": "Invalid credentials. Invalid username or password.",
        }), 403

    token = result.get("accessToken", "")
    _session_cache[username.lower()] = {
        "service_id": service_id,
        "access_token": token,
        "client_token": result.get("clientToken"),
    }

    database.set_player_service(username, service_id)

    logger.info(f"Authenticate: {username} -> service {service_id}")
    return jsonify(result)


@authserver_bp.route("/authserver/refresh", methods=["POST"])
def refresh():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid request"}), 400

    username = payload.get("selectedProfile", {}).get("name", "")
    if not username:
        username = payload.get("username", "")

    cached = _session_cache.get(username.lower())
    if cached:
        service_id = cached["service_id"]
        from config import get_auth_servers
        servers = [s for s in get_auth_servers() if s.get("enabled")]
        server = next((s for s in servers if s.get("priority") == service_id), None)
        if server:
            result = asyncio.run(upstream.refresh_for_server(server, payload))
            if result:
                _session_cache[username.lower()] = {
                    "service_id": service_id,
                    "access_token": result.get("accessToken"),
                    "client_token": result.get("clientToken"),
                }
                return jsonify(result)

    from config import get_auth_servers
    servers = [s for s in get_auth_servers() if s.get("enabled")]
    sorted_servers = sorted(servers, key=lambda s: s.get("priority", 999))
    for server in sorted_servers:
        result = asyncio.run(upstream.refresh_for_server(server, payload))
        if result:
            sid = server.get("priority", 999)
            _session_cache[username.lower()] = {
                "service_id": sid,
                "access_token": result.get("accessToken"),
                "client_token": result.get("clientToken"),
            }
            database.set_player_service(username, sid)
            return jsonify(result)

    return jsonify({
        "error": "ForbiddenOperationException",
        "errorMessage": "Invalid token.",
    }), 403


@authserver_bp.route("/authserver/validate", methods=["POST"])
def validate():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({}), 204

    username = payload.get("selectedProfile", {}).get("name", "")
    cached = _session_cache.get(username.lower()) if username else None

    if cached:
        from config import get_auth_servers
        servers = [s for s in get_auth_servers() if s.get("enabled")]
        server = next((s for s in servers if s.get("priority") == cached["service_id"]), None)
        if server:
            result = asyncio.run(upstream.validate_for_server(server, payload))
            if result is not None:
                return jsonify({}), 204

    return jsonify({
        "error": "ForbiddenOperationException",
        "errorMessage": "Invalid token.",
    }), 403


@authserver_bp.route("/authserver/invalidate", methods=["POST"])
def invalidate():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({}), 204

    username = payload.get("selectedProfile", {}).get("name", "")
    if username:
        cached = _session_cache.pop(username.lower(), None)
        if cached:
            from config import get_auth_servers
            servers = [s for s in get_auth_servers() if s.get("enabled")]
            server = next((s for s in servers if s.get("priority") == cached["service_id"]), None)
            if server:
                asyncio.run(upstream.invalidate_for_server(server, payload))

    return jsonify({}), 204


@authserver_bp.route("/authserver/signout", methods=["POST"])
def signout():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({}), 204

    username = payload.get("username", "")
    if username:
        _session_cache.pop(username.lower(), None)

    from config import get_auth_servers
    servers = [s for s in get_auth_servers() if s.get("enabled")]
    for server in servers:
        asyncio.run(upstream.signout_for_server(server, payload))

    return jsonify({}), 204
