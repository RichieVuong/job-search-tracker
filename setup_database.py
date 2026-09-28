"""Run locally: prompts for the database password without displaying it."""
import getpass
import json
from urllib.parse import quote

from db_config import CONFIG_FILE


def main():
    if CONFIG_FILE.exists():
        print('Database configuration already exists. No changes made.')
        return
    password = getpass.getpass('Supabase database password (hidden): ')
    if not password:
        print('No password entered. Nothing saved.')
        return
    url = 'postgresql://postgres.eanzyffaaynftoyegmvp:' + quote(password, safe='') + '@aws-0-us-east-1.pooler.supabase.com:5432/postgres'
    import psycopg
    try:
        with psycopg.connect(url, sslmode='require', connect_timeout=10) as connection:
            connection.execute('SELECT 1')
    except psycopg.Error:
        print('Connection failed. Check your database password and project status. Nothing saved.')
        return
    with CONFIG_FILE.open('x') as config:
        json.dump({'DATABASE_URL': url}, config)
    print('Connection verified. Private local configuration saved. Your SQLite data has not been moved yet.')


if __name__ == '__main__':
    main()
