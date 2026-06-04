import logging
from flask import Blueprint, request, jsonify

import async_utils
import upstream
import database
import session_store

logger = logging.getLogger(__name__)

authserver_bp = Blueprint("authserver", __name__)


@authserver_bp.route("/authserver/authenticate", methods=["POST"])
def authenticate():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "ForbiddenOperationException", "errorMessage": "Invalid request"}), 400

    username = payload.get("username", "")
    result, service_id = async_utils.run_async(upstream.try_authenticate_all(payload))

    if result is None:
        return jsonify({
            "error": "ForbiddenOperationException",
            "errorMessage": "Invalid credentials. Invalid username or password.",
        }), 403

    session_store.record_auth(username, service_id, result.get("accessToken"), result.get("clientToken"))
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

    cached = session_store.get_by_username(username)
    if cached:
        from config import get_server_by_id
        server = get_server_by_id(cached["service_id"])
        if server:
            result = async_utils.run_async(upstream.auth_action(server, "refresh", payload))
            if result:
                session_store.update(username, result.get("accessToken"), result.get("clientToken"))
                return jsonify(result)

    from config import get_auth_servers
    servers = sorted([s for s in get_auth_servers() if s.get("enabled")], key=lambda s: s.get("priority", 999))
    for server in servers:
        result = async_utils.run_async(upstream.auth_action(server, "refresh", payload))
        if result:
            session_store.record_auth(username, server["id"], result.get("accessToken"), result.get("clientToken"))
            database.set_player_service(username, server["id"])
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
    cached = session_store.get_by_username(username) if username else None

    if cached:
        from config import get_server_by_id
        server = get_server_by_id(cached["service_id"])
        if server:
            result = async_utils.run_async(upstream.auth_action(server, "validate", payload))
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
        cached = session_store.remove(username)
        if cached:
            from config import get_server_by_id
            server = get_server_by_id(cached["service_id"])
            if server:
                async_utils.run_async(upstream.auth_action(server, "invalidate", payload))

    return jsonify({}), 204


@authserver_bp.route("/authserver/signout", methods=["POST"])
def signout():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({}), 204

    username = payload.get("username", "")
    if username:
        session_store.remove(username)

    from config import get_auth_servers
    for server in get_auth_servers():
        if server.get("enabled"):
            async_utils.run_async(upstream.auth_action(server, "signout", payload))

    return jsonify({}), 204
