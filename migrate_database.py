"""Copy SQLite records to Supabase without deleting or overwriting either side.

Dry run: python migrate_database.py
Apply owned records: python migrate_database.py --apply
Assign legacy rows only after confirming identity: --legacy-owner GOOGLE_SUBJECT_ID
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import database


def migrate(apply=False, legacy_owner=None):
    source = Path(database.DATABASE_FILE)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as local:
        local.row_factory = sqlite3.Row
        applications = [dict(row) for row in local.execute('SELECT * FROM applications')]
        goals = [dict(row) for row in local.execute('SELECT * FROM goals')]
    owners = {row['user_id'] for row in applications + goals if row.get('user_id')}
    unassigned = sum(not row.get('user_id') for row in applications)
    print(f'Local: {len(applications)} applications, {len(goals)} goals, {len(owners)} distinct owners, {unassigned} unassigned applications.')
    if legacy_owner and legacy_owner not in owners:
        raise ValueError('Legacy owner must match an existing local account ID')
    if not apply:
        print('Dry run only. Unassigned records stay local unless a verified legacy owner is specified.')
        return
    if not database.DATABASE_URL:
        raise ValueError('Supabase must be configured')
    backup_dir = source.parent / 'backups'
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / ('applications-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.db')
    with sqlite3.connect(source) as local, sqlite3.connect(backup) as dest:
        local.backup(dest)
    database.initialize_database()
    imported = skipped = 0
    with database.get_connection() as target:
        target.execute('CREATE TABLE IF NOT EXISTS local_imports (source TEXT NOT NULL, kind TEXT NOT NULL, local_id BIGINT NOT NULL, remote_id BIGINT NOT NULL, PRIMARY KEY(source,kind,local_id))')
        # Serialize reruns so the ledger and inserted rows remain atomic.
        target.execute('LOCK TABLE local_imports IN EXCLUSIVE MODE')
        for kind, rows in (('applications', applications), ('goals', goals)):
            for row in rows:
                owner = row.get('user_id') or legacy_owner
                if not owner:
                    skipped += 1
                    continue
                key = ('original-local-tracker', kind, row['id'])
                if target.execute('SELECT remote_id FROM local_imports WHERE source=? AND kind=? AND local_id=?', key).fetchone():
                    skipped += 1
                    continue
                if kind == 'applications':
                    fields = ('company','role','status','created_at','updated_at','job_url','notes')
                    if not row['created_at'] or not row['updated_at']:
                        raise ValueError('Missing dates in source; migration rolled back')
                    result = target.execute('INSERT INTO applications(user_id,company,role,status,created_at,updated_at,job_url,notes) VALUES(?,?,?,?,?,?,?,?) RETURNING id', (owner, *(row.get(field) or '' for field in fields)))
                else:
                    result = target.execute('INSERT INTO goals(user_id,text,completed) VALUES(?,?,?) RETURNING id', (owner,row['text'],row['completed']))
                remote_id = result.fetchone()['id']
                target.execute('INSERT INTO local_imports(source,kind,local_id,remote_id) VALUES(?,?,?,?)', (*key,remote_id))
                imported += 1
    print(f'Imported {imported} records; skipped {skipped} unassigned or previously imported records. SQLite and its backup are preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--legacy-owner')
    args = parser.parse_args()
    try:
        migrate(args.apply, args.legacy_owner)
    except Exception as error:
        print('Migration failed; database transaction rolled back:', type(error).__name__)
        raise SystemExit(1)
