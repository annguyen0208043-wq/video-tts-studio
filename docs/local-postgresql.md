# PostgreSQL local

Video TTS Studio can use its own portable PostgreSQL instance. The Windows
binaries come from [EDB](https://www.enterprisedb.com/download-postgresql-binaries),
the distributor linked by PostgreSQL's Windows download page.

- Binaries: `.tools/postgresql/pgsql`
- Database files: `data/postgresql`
- Address: `127.0.0.1:55432`, database `video_tts_studio`
- Application connection and generated password: `DATABASE_URL` in `.env`
- Server log: `logs/postgresql.log`

Open `run.bat` as usual. It starts the local database before running migrations
and the backend. `scripts/run-local.ps1` and `scripts/dev.ps1` do the same.
The database listens only on loopback and requires password authentication.
PostgreSQL stays running when the backend stops; after a Windows restart the
launcher starts it again.

Check the connection:

```powershell
.\.venv\Scripts\python.exe scripts/check-database.py
```

## Initial migration from Supabase

Extract the Windows PostgreSQL 17.11 binary archive so that
`.tools/postgresql/pgsql/bin/pg_ctl.exe` exists. Stop the backend and other
applications writing to the source database. Then run:

```powershell
.\.venv\Scripts\python.exe scripts/migrate-to-local-postgres.py
```

The script creates a password-protected local cluster and an application role,
copies the eight application tables from a consistent read-only source snapshot,
then compares row counts and SHA-256 digests of every row, including voice audio.
It updates only `DATABASE_URL` after verification succeeds. The source database
is unchanged. Existing media files remain in `data`.

The ignored `data/database-backups/<timestamp>/` folder contains the database
dump, original `.env`, local administrator password and verification report.
These files contain private data and credentials; keep them private. Back up
this folder and application media separately. Do not delete `data/postgresql`.

To roll back immediately, stop the backend, restore `.env` from `original.env`
and restart the application. Changes made locally after the switch are not
copied back to Supabase by this procedure.
