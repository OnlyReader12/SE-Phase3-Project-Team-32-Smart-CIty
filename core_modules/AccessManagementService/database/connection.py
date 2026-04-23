"""
database/connection.py — SQLite Connection Manager with WAL Mode.

Provides thread-safe database access for both microservices.
WAL (Write-Ahead Logging) mode enables concurrent reads while one writer
is active — perfect for our ingestion + gateway architecture.

Usage:
    db = DatabaseManager("/path/to/smartcity.db")
    db.initialize()  # creates tables + seeds data
    
    with db.get_connection() as conn:
        conn.execute("SELECT * FROM users")
"""

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


_BASE_DIR = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_DEFAULT_DB_PATH = _BASE_DIR / "smartcity.db"


class DatabaseManager:
    """
    Thread-safe SQLite connection manager.
    Uses WAL mode for concurrent read/write access across two services.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(_DEFAULT_DB_PATH)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=15)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def get_connection(self) -> sqlite3.Connection:
        """Public accessor for a thread-local connection."""
        return self._get_conn()

    def initialize(self) -> None:
        """Create all tables from schema.sql if they don't exist."""
        conn = self._get_conn()
        with open(_SCHEMA_PATH, "r") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()
        print(f"[DB] Schema initialized: {self.db_path}")

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement."""
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor

    def executemany(self, sql: str, params_list: list) -> None:
        """Execute a SQL statement for multiple parameter sets."""
        conn = self._get_conn()
        conn.executemany(sql, params_list)
        conn.commit()

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dict."""
        conn = self._get_conn()
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows as a list of dicts."""
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
