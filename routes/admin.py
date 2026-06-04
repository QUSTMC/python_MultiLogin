import asyncio
import uuid
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, redirect, url_for

from config import get_auth_servers, update_auth_servers, get_config, update_config, get_server_setting, generate_server_id
from auth_key import verify_key
from upstream import check_server_status
import database

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

    data["id"] = generate_server_id(data["name"], data["url"])

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


@admin_bp.route("/admin/api/servers/reorder", methods=["POST"])
@require_key
def reorder_servers():
    data = request.get_json(silent=True)
    if not data or "order" not in data:
        return jsonify({"error": "Invalid request"}), 400

    order = data["order"]
    servers = get_auth_servers()
    server_map = {s["id"]: s for s in servers}

    reordered = []
    for i, entry in enumerate(order):
        sid = entry.get("id")
        if sid and sid in server_map:
            s = server_map[sid]
            s["priority"] = i + 1
            reordered.append(s)

    remaining = [s for s in servers if s not in reordered]
    for i, s in enumerate(remaining):
        s["priority"] = len(reordered) + i + 1
    reordered.extend(remaining)

    update_auth_servers(reordered)
    return jsonify(reordered)


@admin_bp.route("/admin/api/settings", methods=["GET"])
@require_key
def get_settings():
    cfg = get_config()
    server = cfg.get("server", {})
    return jsonify({
        "host": server.get("host", "0.0.0.0"),
        "port": server.get("port", 8080),
        "skin_restorer": cfg.get("skin_restorer", "off"),
        "skin_restorer_method": cfg.get("skin_restorer_method", "url"),
        "allow_duplicate_names": cfg.get("allow_duplicate_names", False),
    })


@admin_bp.route("/admin/api/settings", methods=["PUT"])
@require_key
def update_settings():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    cfg = get_config()
    server = cfg.get("server", {})

    if "port" in data:
        port = int(data["port"])
        if port < 1 or port > 65535:
            return jsonify({"error": "Port must be 1-65535"}), 400
        server["port"] = port

    if "host" in data:
        server["host"] = str(data["host"])

    cfg["server"] = server

    if "skin_restorer" in data:
        cfg["skin_restorer"] = str(data["skin_restorer"]).lower()
    if "skin_restorer_method" in data:
        cfg["skin_restorer_method"] = str(data["skin_restorer_method"]).lower()
    if "allow_duplicate_names" in data:
        cfg["allow_duplicate_names"] = bool(data["allow_duplicate_names"])

    update_config(cfg)
    return jsonify({
        "host": server.get("host"),
        "port": server.get("port"),
        "skin_restorer": cfg.get("skin_restorer", "off"),
        "skin_restorer_method": cfg.get("skin_restorer_method", "url"),
        "allow_duplicate_names": cfg.get("allow_duplicate_names", False),
    })


@admin_bp.route("/admin/api/bindings", methods=["GET"])
@require_key
def get_bindings():
    keyword = request.args.get("q", "").strip()
    if keyword:
        bindings = database.search_name_binding(keyword)
    else:
        bindings = database.list_name_bindings()
    return jsonify(bindings)


@admin_bp.route("/admin/api/bindings/<username>", methods=["DELETE"])
@require_key
def delete_binding(username: str):
    deleted = database.delete_name_binding(username)
    if deleted:
        return jsonify({"deleted": username})
    return jsonify({"error": "Binding not found"}), 404


@admin_bp.route("/admin/api/bans", methods=["GET"])
@require_key
def get_bans():
    keyword = request.args.get("q", "").strip()
    if keyword:
        bans = database.search_bans(keyword)
    else:
        bans = database.list_bans()
    return jsonify(bans)


@admin_bp.route("/admin/api/bans", methods=["POST"])
@require_key
def add_ban():
    data = request.get_json(silent=True)
    if not data or not data.get("target") or not data.get("ban_type"):
        return jsonify({"error": "Missing required fields: target, ban_type"}), 400

    ban_type = data["ban_type"]
    if ban_type not in ("name", "uuid"):
        return jsonify({"error": "ban_type must be 'name' or 'uuid'"}), 400

    database.add_ban(data["target"], ban_type, data.get("reason", ""))
    return jsonify({"added": data["target"], "ban_type": ban_type}), 201


@admin_bp.route("/admin/api/bans/<int:ban_id>", methods=["DELETE"])
@require_key
def delete_ban(ban_id: int):
    deleted = database.remove_ban(ban_id)
    if deleted:
        return jsonify({"deleted": ban_id})
    return jsonify({"error": "Ban not found"}), 404
