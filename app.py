import logging
import sys

from flask import Flask

import config
import database
from auth_key import load_or_create_key
from routes.authserver import authserver_bp
from routes.session import session_bp
from routes.admin import admin_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("multilogin")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
    )

    app.register_blueprint(authserver_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return {"status": "ok", "service": "MultiLogin Python"}, 200

    return app


def main():
    cfg = config.load_config()
    server_cfg = cfg.get("server", {})

    key = load_or_create_key()
    if not server_cfg.get("access_key"):
        server_cfg["access_key"] = key
        config.save_config()
        print("=" * 60)
        print(f"  Access Key (first run): {key}")
        print(f"  Admin URL: http://localhost:{server_cfg.get('port', 8080)}/admin/")
        print("=" * 60)
    else:
        logger.info(f"Admin URL: http://localhost:{server_cfg.get('port', 8080)}/admin/")

    database.init_db()

    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 8080)

    logger.info(f"Starting MultiLogin Python on {host}:{port}")
    logger.info(f"Loaded {len(config.get_auth_servers())} auth server(s)")

    app = create_app()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
