"""One-time copy of public application tables to the portable local cluster.

Requires PostgreSQL binaries under .tools/postgresql/pgsql. The source is read
only; .env is switched only after every row has been verified.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from datetime import datetime

import psycopg
from psycopg import sql
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import make_url, URL

from start_local_postgres import PG_BIN, PG_DATA, PORT, ROOT


def run(name, args, env=None):
    if name == 'pg_ctl':
        # postgres inherits pg_ctl's handles on Windows; pipes would stay open
        # for the server's lifetime and block subprocess.communicate().
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as output:
            result = subprocess.run([str(PG_BIN / 'pg_ctl.exe'), *args], env=env,
                                    stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
            output.seek(0)
            message = output.read()
        if result.returncode:
            raise RuntimeError('pg_ctl failed: ' + message)
        return message
    result = subprocess.run([str(PG_BIN / (name + '.exe')), *args], env=env,
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        # Native utilities receive passwords only in the environment/password file.
        raise RuntimeError(f'{name} failed: {result.stderr}')
    return result.stdout


def connect(url):
    return psycopg.connect(host=url.host, port=url.port or 5432, user=url.username,
                          password=url.password, dbname=url.database, connect_timeout=20,
                          options='-c timezone=UTC -c extra_float_digits=3')


def digest(connection, table):
    # JSON encodes bytea, timestamps and JSON fields consistently on both servers.
    query = sql.SQL('SELECT row_to_json(t)::text FROM public.{} t ORDER BY id COLLATE "C"').format(sql.Identifier(table))
    if table == 'alembic_version':
        query = sql.SQL('SELECT row_to_json(t)::text FROM public.{} t ORDER BY version_num').format(sql.Identifier(table))
    checksum = hashlib.sha256()
    count = 0
    with connection.cursor(name='verify_' + table) as cursor:
        cursor.execute(query)
        for (row,) in cursor:
            checksum.update(row.encode('utf-8'))
            checksum.update(b'\n')
            count += 1
    return {'rows': count, 'sha256': checksum.hexdigest()}


def main():
    source = make_url(dotenv_values(ROOT / '.env')['DATABASE_URL'])
    if source.host in {'127.0.0.1', 'localhost'}:
        raise RuntimeError('The configured database is already local; nothing was changed.')
    resume = '--resume' in sys.argv
    verify_existing = '--verify-existing' in sys.argv
    refresh_existing = '--refresh-existing' in sys.argv
    if verify_existing and not resume:
        raise RuntimeError('--verify-existing requires --resume <backup timestamp>.')
    if PG_DATA.exists() and not resume:
        raise RuntimeError('Local cluster already exists; refusing to overwrite it.')
    if not resume:
        with socket.socket() as check:
            check.bind(('127.0.0.1', PORT))
    backup = (ROOT / 'data' / 'database-backups' / sys.argv[sys.argv.index('--resume') + 1]
              if resume else ROOT / 'data' / 'database-backups' / datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, exist_ok=resume)
    # Preserve all original settings for rollback, including the source connection.
    if not resume:
        (backup / 'original.env').write_bytes((ROOT / '.env').read_bytes())
    app_password = secrets.token_urlsafe(32)
    (backup / 'local-app-password').write_text(app_password, encoding='utf-8')
    admin_password = ((backup / 'local-admin-password').read_text(encoding='utf-8')
                      if resume else secrets.token_urlsafe(32))
    (backup / 'local-admin-password').write_text(admin_password, encoding='utf-8')
    pwfile = backup / 'init-password'
    if not resume:
        pwfile.write_text(admin_password, encoding='utf-8')
    try:
        if not resume:
            print('Initializing local PostgreSQL...', flush=True)
            run('initdb', ['-D', str(PG_DATA), '-U', 'postgres', '--encoding=UTF8',
                           '--locale=C', '--auth=scram-sha-256', '--pwfile=' + str(pwfile)])
    finally:
        pwfile.unlink(missing_ok=True)
    with (PG_DATA / 'postgresql.conf').open('a', encoding='utf-8') as config:
        config.write(f"\n# Video TTS Studio portable local instance\nlisten_addresses = '127.0.0.1'\nport = {PORT}\n")
    (ROOT / 'logs').mkdir(exist_ok=True)
    if not resume:
        run('pg_ctl', ['-D', str(PG_DATA), '-l', str(ROOT / 'logs' / 'postgresql.log'), '-w', 'start'])
    with psycopg.connect(host='127.0.0.1', port=PORT, user='postgres', password=admin_password,
                          dbname='postgres', autocommit=True) as admin:
        command = 'ALTER ROLE video_tts_app LOGIN PASSWORD {}' if verify_existing or refresh_existing else 'CREATE ROLE video_tts_app LOGIN PASSWORD {}'
        admin.execute(sql.SQL(command).format(sql.Literal(app_password)))
        if not verify_existing and not refresh_existing:
            admin.execute('CREATE DATABASE video_tts_studio OWNER video_tts_app')
    target = URL.create('postgresql+psycopg', username='video_tts_app', password=app_password,
                        host='127.0.0.1', port=PORT, database='video_tts_studio')
    expected = {'alembic_version', 'projects', 'assets', 'sequences', 'sequence_items',
                'jobs', 'bgm_tracks', 'voice_library'}
    with connect(source) as remote:
        remote.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        tables = set(row[0] for row in remote.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        if tables != expected:
            raise RuntimeError(f'Unexpected source tables: {sorted(tables)}. Configuration was not switched.')
        snapshot = remote.execute('SELECT pg_export_snapshot()').fetchone()[0]
        dump = backup / 'application.dump'
        source_env = dict(os.environ, PGPASSWORD=source.password, PGCONNECT_TIMEOUT='20')
        args = ['-h', source.host, '-p', str(source.port or 5432), '-U', source.username,
                '-d', source.database, '-Fc', '--no-owner', '--no-acl', '--snapshot=' + snapshot,
                '-f', str(dump)]
        for table in sorted(tables):
            args += ['-t', 'public.' + table]
        if not verify_existing:
            print('Backing up a consistent snapshot of application tables...', flush=True)
            run('pg_dump', args, source_env)
            print('Restoring to local PostgreSQL...', flush=True)
            run('pg_restore', (['--clean', '--if-exists'] if refresh_existing else []) + ['-h', '127.0.0.1', '-p', str(PORT), '-U', 'video_tts_app',
                              '-d', 'video_tts_studio', '--no-owner', '--no-acl', '--exit-on-error', str(dump)],
                dict(os.environ, PGPASSWORD=app_password))
        report = {}
        with connect(target) as local:
            for table in sorted(tables):
                original = digest(remote, table)
                copied = digest(local, table)
                if copied != original:
                    raise RuntimeError(f'Verification failed for {table}; .env was not changed.')
                report[table] = copied
                print(f'Verified {table}: {copied["rows"]} rows', flush=True)
        (backup / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    set_key(str(ROOT / '.env'), 'DATABASE_URL', target.render_as_string(hide_password=False), quote_mode='never')
    print('Switched .env to 127.0.0.1:55432/video_tts_studio. Source database unchanged.', flush=True)
    print('Backup: ' + str(backup), flush=True)


if __name__ == '__main__':
    main()
