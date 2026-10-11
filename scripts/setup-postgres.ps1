$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PsqlCommand = Get-Command psql -ErrorAction SilentlyContinue
$Psql = if ($PsqlCommand) { $PsqlCommand.Source } else { $null }

if (-not $Psql) {
    $Candidates = @(Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
    if ($Candidates.Count -gt 0) { $Psql = $Candidates[0].FullName }
}
if (-not $Psql) {
    throw "psql was not found. Install PostgreSQL and run this script again."
}

$AdminPasswordSecure = Read-Host "Enter the postgres admin password" -AsSecureString
$AdminPassword = [System.Net.NetworkCredential]::new("", $AdminPasswordSecure).Password
$AppPasswordSecure = Read-Host "Create a NEW password for video_tts_app (minimum 10 characters)" -AsSecureString
$AppPassword = [System.Net.NetworkCredential]::new("", $AppPasswordSecure).Password
if ($AppPassword.Length -lt 10) {
    throw "The application password must contain at least 10 characters."
}

$EscapedPassword = $AppPassword.Replace("'", "''")
$Sql = "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='video_tts_app') THEN CREATE ROLE video_tts_app LOGIN PASSWORD '$EscapedPassword'; ELSE ALTER ROLE video_tts_app PASSWORD '$EscapedPassword'; END IF; END `$`$;"

try {
    $env:PGPASSWORD = $AdminPassword
    & $Psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "Could not create the PostgreSQL role." }

    $Exists = & $Psql -U postgres -h 127.0.0.1 -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='video_tts_studio'"
    if ($LASTEXITCODE -ne 0) { throw "Could not check the PostgreSQL database." }
    if ($Exists -ne "1") {
        & $Psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE video_tts_studio OWNER video_tts_app"
        if ($LASTEXITCODE -ne 0) { throw "Could not create the video_tts_studio database." }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $AdminPassword = $null
}

$Encoded = [uri]::EscapeDataString($AppPassword)
$EnvPath = Join-Path $ProjectRoot ".env"
$EnvContent = @"
DATABASE_URL=postgresql+psycopg://video_tts_app:$Encoded@127.0.0.1:5432/video_tts_studio
APP_HOST=127.0.0.1
APP_PORT=8765
DATA_DIR=./data
LOG_DIR=./logs
VIENEU_REPO=../VieNeu-TTS
TTS_DEVICE=auto
MAX_SEQUENCE_OUTPUTS=100
MAX_UPLOAD_MB=4096
MAX_CONCURRENT_JOBS=3
VIENEU_OFFLINE=1
"@
[System.IO.File]::WriteAllText($EnvPath, $EnvContent, [System.Text.UTF8Encoding]::new($false))
$AppPassword = $null
Write-Host "Database, application role, and .env were created successfully." -ForegroundColor Green
