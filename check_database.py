"""Verify configuration without printing credentials or connection errors."""
import sqlite3
from urllib.parse import urlsplit, unquote
import database


def main():
    if not database.DATABASE_URL:
        print('Supabase is not configured.')
        return 1
    try:
        database.initialize_database()
        with database.get_connection() as connection:
            for table in ('applications', 'goals'):
                count = connection.execute(f'SELECT COUNT(*) AS count FROM {table}').fetchone()['count']
                print(f'Supabase {table}: {count} records')
        print('Supabase connection verified; private tables ready.')
        with sqlite3.connect(f'file:{database.DATABASE_FILE}?mode=ro', uri=True) as local:
            total, unassigned = local.execute('SELECT COUNT(*), SUM(user_id IS NULL) FROM applications').fetchone()
            print(f'Local applications still preserved: {total}; unassigned: {unassigned or 0}')
        return 0
    except Exception as error:
        print('Database check failed:', type(error).__name__)
        message = str(error).lower()
        # Strip connection credentials before reporting the diagnostic.
        safe_message = str(error).replace(database.DATABASE_URL, '[database URL]')
        password = urlsplit(database.DATABASE_URL).password
        if password:
            safe_message = safe_message.replace(password, '[redacted]').replace(unquote(password), '[redacted]')
        print(safe_message)
        for marker, hint in (
            ('tenant or user not found', 'Supabase project may be paused, or the pooler username is no longer valid. Check project status.'),
            ('password authentication failed', 'Database password was rejected.'),
            ('timeout', 'Connection timed out. Check network access and whether the Supabase project is running.'),
            ('resolve', 'Could not resolve the database hostname.'),
            ('refused', 'Database refused the connection.'),
        ):
            if marker in message:
                print(hint)
                break
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
