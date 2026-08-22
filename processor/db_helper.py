"""
RoninClips — Unified Database Helper
Supports transparent switching between SQLite (zero-config local default)
and MySQL based on DB_CONNECTION in the root .env file.

Normalizes query placeholders (%s <-> ?) and row dictionary formatting.
"""

import os
import sys
import sqlite3
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(ROOT_DIR, '.env'))


class UnifiedCursor:
    """Wrapper around sqlite3 or mysql cursor to provide consistent dictionary results."""
    
    def __init__(self, raw_cursor, is_sqlite=False):
        self.raw_cursor = raw_cursor
        self.is_sqlite = is_sqlite

    def execute(self, query, params=None):
        if self.is_sqlite:
            # Normalize MySQL %s placeholders to SQLite ? placeholders
            # only if not already using ? placeholders
            if '%s' in query and '?' not in query:
                normalized_query = query.replace('%s', '?')
            else:
                normalized_query = query
            
            if params is None:
                return self.raw_cursor.execute(normalized_query)
            elif isinstance(params, (list, tuple)):
                return self.raw_cursor.execute(normalized_query, params)
            else:
                return self.raw_cursor.execute(normalized_query, (params,))
        else:
            if params is None:
                return self.raw_cursor.execute(query)
            elif isinstance(params, (list, tuple)):
                return self.raw_cursor.execute(query, params)
            else:
                return self.raw_cursor.execute(query, (params,))

    def fetchone(self):
        row = self.raw_cursor.fetchone()
        if row is None:
            return None
        if self.is_sqlite:
            # Convert sqlite3.Row to dict
            return dict(row)
        return row

    def fetchall(self):
        rows = self.raw_cursor.fetchall()
        if self.is_sqlite:
            return [dict(r) for r in rows]
        return rows

    @property
    def lastrowid(self):
        return self.raw_cursor.lastrowid

    @property
    def rowcount(self):
        return self.raw_cursor.rowcount

    def close(self):
        self.raw_cursor.close()


class UnifiedDB:
    """Wrapper managing the underlying SQLite or MySQL connection."""

    def __init__(self, connection, is_sqlite=False, driver_name="sqlite"):
        self.connection = connection
        self.is_sqlite = is_sqlite
        self.driver_name = driver_name

    def cursor(self):
        if self.is_sqlite:
            raw = self.connection.cursor()
            return UnifiedCursor(raw, is_sqlite=True)
        else:
            raw = self.connection.cursor(dictionary=True)
            return UnifiedCursor(raw, is_sqlite=False)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        try:
            self.connection.close()
        except Exception:
            pass


def get_db():
    """
    Connect to database using .env configuration.
    Defaults to SQLite if DB_CONNECTION is not set or set to 'sqlite'.
    """
    driver = os.environ.get('DB_CONNECTION', 'sqlite').lower().strip()

    if driver == 'mysql':
        try:
            import mysql.connector
            db_host = os.environ.get("DB_HOST", "127.0.0.1")
            db_user = os.environ.get("DB_USERNAME", "root")
            db_password = os.environ.get("DB_PASSWORD", "")
            db_name = os.environ.get("DB_DATABASE", "roninclips")
            db_port = int(os.environ.get("DB_PORT", 3306))

            conn = mysql.connector.connect(
                host=db_host,
                user=db_user,
                password=db_password,
                database=db_name,
                port=db_port
            )
            return UnifiedDB(conn, is_sqlite=False, driver_name="mysql")
        except Exception as e:
            print(f"[db_helper] MySQL connection failed: {e}")
            print("[db_helper] Falling back to SQLite...")
            driver = 'sqlite'

    # SQLite connection (default / fallback)
    db_path_env = os.environ.get('DB_DATABASE', '')
    if db_path_env and os.path.isabs(db_path_env):
        sqlite_file = db_path_env
    elif db_path_env and not db_path_env.endswith('.sqlite') and not db_path_env.endswith('.db'):
        # In case DB_DATABASE was set to a MySQL database name like 'roninclips'
        sqlite_file = os.path.join(ROOT_DIR, 'database', 'database.sqlite')
    elif db_path_env:
        sqlite_file = os.path.join(ROOT_DIR, db_path_env)
    else:
        sqlite_file = os.path.join(ROOT_DIR, 'database', 'database.sqlite')

    os.makedirs(os.path.dirname(sqlite_file), exist_ok=True)
    
    # Touch file if it doesn't exist
    if not os.path.exists(sqlite_file):
        open(sqlite_file, 'a').close()

    conn = sqlite3.connect(sqlite_file, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high-concurrency read/writes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    
    return UnifiedDB(conn, is_sqlite=True, driver_name="sqlite")


def get_driver_name():
    """Return the active database driver name ('sqlite' or 'mysql')."""
    return os.environ.get('DB_CONNECTION', 'sqlite').lower().strip()
