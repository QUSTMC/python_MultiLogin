import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "data.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def get_conn() -> sqlite3.Connection:
    return _get_conn()


def init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS player_service_map (
            username TEXT PRIMARY KEY,
            service_id INTEGER NOT NULL,
            online_uuid TEXT,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS in_game_profile (
            online_uuid TEXT NOT NULL,
            service_id INTEGER NOT NULL,
            in_game_uuid TEXT NOT NULL,
            in_game_name TEXT,
            PRIMARY KEY (online_uuid, service_id)
        );

        CREATE TABLE IF NOT EXISTS uuid_service_map (
            uuid TEXT PRIMARY KEY,
            service_id INTEGER NOT NULL,
            username TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def close_db() -> None:
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def get_player_service(username: str) -> int | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT service_id FROM player_service_map WHERE username = ?",
        (username,),
    ).fetchone()
    return row["service_id"] if row else None


def set_player_service(username: str, service_id: int, online_uuid: str | None = None) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO player_service_map (username, service_id, online_uuid, last_login)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(username) DO UPDATE SET
               service_id = excluded.service_id,
               online_uuid = COALESCE(excluded.online_uuid, online_uuid),
               last_login = CURRENT_TIMESTAMP""",
        (username, service_id, online_uuid),
    )
    conn.commit()


def get_in_game_profile(online_uuid: str, service_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM in_game_profile WHERE online_uuid = ? AND service_id = ?",
        (online_uuid, service_id),
    ).fetchone()
    return dict(row) if row else None


def set_in_game_profile(online_uuid: str, service_id: int, in_game_uuid: str, in_game_name: str | None = None) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO in_game_profile (online_uuid, service_id, in_game_uuid, in_game_name)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(online_uuid, service_id) DO UPDATE SET
               in_game_uuid = excluded.in_game_uuid,
               in_game_name = COALESCE(excluded.in_game_name, in_game_name)""",
        (online_uuid, service_id, in_game_uuid, in_game_name),
    )
    conn.commit()


def get_service_by_uuid(uuid: str) -> int | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT service_id FROM uuid_service_map WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    return row["service_id"] if row else None


def set_uuid_service(uuid: str, service_id: int, username: str | None = None) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO uuid_service_map (uuid, service_id, username, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(uuid) DO UPDATE SET
               service_id = excluded.service_id,
               username = COALESCE(excluded.username, username),
               updated_at = CURRENT_TIMESTAMP""",
        (uuid, service_id, username),
    )
    conn.commit()
