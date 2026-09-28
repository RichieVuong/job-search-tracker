import sqlite3
from db_config import database_url
from contextlib import contextmanager


from pathlib import Path

DATABASE_FILE = str(Path(__file__).with_name("applications.db"))
DATABASE_URL = database_url()


class PostgresConnection:
    """Adapt this module's parameterized SQLite queries for PostgreSQL."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s').replace('LIKE %s COLLATE NOCASE', 'ILIKE %s')
        sql = sql.replace('CURRENT_TIMESTAMP', "to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS')")
        return self.connection.execute(sql, params)


@contextmanager
def get_connection():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(DATABASE_URL, sslmode='require', connect_timeout=10, row_factory=dict_row) as connection:
            connection.execute('SET search_path TO tracker_private')
            yield PostgresConnection(connection)
        return
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        if DATABASE_URL:
            connection.execute('CREATE SCHEMA IF NOT EXISTS tracker_private')
            connection.execute('REVOKE ALL ON SCHEMA tracker_private FROM PUBLIC, anon, authenticated')
            connection.execute("CREATE TABLE IF NOT EXISTS applications (id BIGSERIAL PRIMARY KEY, user_id TEXT NOT NULL, company TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, job_url TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '')")
            connection.execute('CREATE INDEX IF NOT EXISTS applications_owner ON applications(user_id)')
            connection.execute('CREATE TABLE IF NOT EXISTS goals (id BIGSERIAL PRIMARY KEY, user_id TEXT NOT NULL, text TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)')
            connection.execute('CREATE INDEX IF NOT EXISTS goals_owner ON goals(user_id)')
            return
        connection.execute("CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, text TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(applications)")}
        for field in ("job_url", "notes"):
            if field not in columns:
                connection.execute(f"ALTER TABLE applications ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        if "user_id" not in columns:
            connection.execute("ALTER TABLE applications ADD COLUMN user_id TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS applications_owner ON applications(user_id)")
        if "created_at" not in columns:
            connection.execute("ALTER TABLE applications ADD COLUMN created_at TEXT")
            connection.execute("UPDATE applications SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        if "updated_at" not in columns:
            connection.execute("ALTER TABLE applications ADD COLUMN updated_at TEXT")
            connection.execute("UPDATE applications SET updated_at = created_at WHERE updated_at IS NULL")


def list_goals(user_id):
    with get_connection() as connection:
        return [dict(row) for row in connection.execute("SELECT id, text, completed FROM goals WHERE user_id=? ORDER BY id DESC", (user_id,))]


def add_goal(user_id, text):
    with get_connection() as connection:
        cursor = connection.execute("INSERT INTO goals(user_id,text) VALUES(?,?) RETURNING id", (user_id,text))
        return {"id":cursor.fetchone()['id'], "text":text, "completed":False}


def set_goal_completed(user_id, goal_id, completed):
    with get_connection() as connection:
        return connection.execute("UPDATE goals SET completed=? WHERE user_id=? AND id=?", (int(completed),user_id,goal_id)).rowcount > 0


def create_application(user_id, company, role, status):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO applications (user_id, company, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (user_id, company, role, status),
        )
        application_id = cursor.fetchone()['id']

    return get_application_by_id(user_id, application_id)


def get_application_by_id(user_id, application_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM applications WHERE user_id = ? AND id = ?",
            (user_id, application_id),
        ).fetchone()

    return dict(row) if row else None


def update_application_status(user_id, application_id, status):
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE applications SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND id = ?",
            (status, user_id, application_id),
        )

    if cursor.rowcount == 0:
        return None

    return get_application_by_id(user_id, application_id)


def update_application_details(user_id, application_id, company, role, job_url, notes):
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE applications SET company=?, role=?, job_url=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND id=?",
            (company, role, job_url, notes, user_id, application_id),
        )
    return get_application_by_id(user_id, application_id) if cursor.rowcount else None


def delete_application(user_id, application_id):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM applications WHERE user_id = ? AND id = ?",
            (user_id, application_id),
        )

    return cursor.rowcount > 0


def get_recent_applications(user_id, limit=20):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM applications WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_application_count(user_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM applications WHERE user_id = ?", (user_id,)
        ).fetchone()

    return row["count"]


def get_applications_by_statuses(user_id, statuses):
    placeholders = ", ".join("?" for _ in statuses)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM applications WHERE user_id = ? AND status IN ({placeholders}) ORDER BY id DESC",
            (user_id, *statuses),
        ).fetchall()

    return [dict(row) for row in rows]


def get_status_counts(user_id):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM applications WHERE user_id = ? GROUP BY status", (user_id,)
        ).fetchall()

    return {row["status"]: row["count"] for row in rows}


def get_activity_dates(user_id):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT created_at FROM applications WHERE user_id = ? AND created_at IS NOT NULL", (user_id,)
        ).fetchall()

    return [row["created_at"] for row in rows]


def search_applications(user_id, company):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM applications
            WHERE user_id = ? AND company LIKE ? COLLATE NOCASE
            ORDER BY id DESC
            """,
            (user_id, f"{company}%"),
        ).fetchall()

    return [dict(row) for row in rows]
