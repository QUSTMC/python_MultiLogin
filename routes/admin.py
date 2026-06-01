import asyncio
import uuid
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, redirect, url_for

from config import get_auth_servers, update_auth_servers, get_config, update_config
from auth_key import verify_key
from upstream import check_server_status

admin_bp = Blueprint("admin", __name__, template_folder="../templates")


def require_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        config = get_config()
        actual_key = config.get("server", {}).get("access_key", "")

        key = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not key:
            key = request.args.get("key", "")

        if not verify_key(key, actual_key):
            if request.path.startswith("/admin/api/"):
                return jsonify({"error": "Unauthorized", "errorMessage": "Invalid access key"}), 401
            return redirect(url_for("admin.login_page"))

        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/admin/")
@require_key
def index():
    return render_template("admin/index.html")


@admin_bp.route("/admin/login")
def login_page():
    return render_template("admin/login.html")


@admin_bp.route("/admin/api/servers", methods=["GET"])
@require_key
def get_servers():
    servers = get_auth_servers()
    return jsonify(servers)


@admin_bp.route("/admin/api/servers", methods=["POST"])
@require_key
def add_server():
    data = request.get_json(silent=True)
    if not data or not data.get("name") or not data.get("url"):
        return jsonify({"error": "Missing required fields: name, url"}), 400

    servers = get_auth_servers()

    if "priority" not in data or data["priority"] is None:
        max_p = max((s.get("priority", 0) for s in servers), default=0)
        data["priority"] = max_p + 1

    data.setdefault("enabled", True)
    data.setdefault("timeout", 10000)
    data.setdefault("track_ip", True)
    data.setdefault("init_uuid", "online")

    servers.append(data)
    update_auth_servers(servers)
    return jsonify(data), 201


@admin_bp.route("/admin/api/servers/<int:idx>", methods=["PUT"])
@require_key
def update_server(idx: int):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    servers = get_auth_servers()
    if idx < 0 or idx >= len(servers):
        return jsonify({"error": "Server not found"}), 404

    servers[idx].update(data)
    update_auth_servers(servers)
    return jsonify(servers[idx])


@admin_bp.route("/admin/api/servers/<int:idx>", methods=["DELETE"])
@require_key
def delete_server(idx: int):
    servers = get_auth_servers()
    if idx < 0 or idx >= len(servers):
        return jsonify({"error": "Server not found"}), 404

    removed = servers.pop(idx)
    update_auth_servers(servers)
    return jsonify({"deleted": removed.get("name", "")})


@admin_bp.route("/admin/api/servers/<int:idx>/toggle", methods=["POST"])
@require_key
def toggle_server(idx: int):
    servers = get_auth_servers()
    if idx < 0 or idx >= len(servers):
        return jsonify({"error": "Server not found"}), 404

    servers[idx]["enabled"] = not servers[idx].get("enabled", True)
    update_auth_servers(servers)
    return jsonify(servers[idx])


@admin_bp.route("/admin/api/servers/check", methods=["POST"])
@require_key
def check_servers():
    servers = get_auth_servers()
    if not servers:
        return jsonify([])

    results = asyncio.run(_check_all_servers(servers))
    return jsonify(results)


async def _check_all_servers(servers: list) -> list:
    tasks = [check_server_status(s) for s in servers]
    return await asyncio.gather(*tasks)
