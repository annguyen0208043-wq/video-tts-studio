<#
.SYNOPSIS
    First-time setup for Video TTS Studio on a fresh Windows machine.
    Run via install.bat or: powershell -ExecutionPolicy Bypass -File .\scripts\first-setup.ps1
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root

Write-Host "=== Video TTS Studio - Cai Dat ===" -ForegroundColor Cyan

# -- 1. Kiem tra Python embedded ----------------------------------------------
Write-Host ""
Write-Host "[1/5] Kiem tra Python..." -ForegroundColor Green
$Python = Join-Path $Root ".python\python.exe"
if (-not (Test-Path $Python)) {
    throw "Thieu .python\python.exe. Ban phan phoi bi hong."
}
& $Python -c "import sys; print('  Python ' + sys.version)"

# -- 2. Tai FFmpeg neu thieu --------------------------------------------------
Write-Host ""
Write-Host "[2/5] Kiem tra FFmpeg..." -ForegroundColor Green
$ffmpegExe = Join-Path $Root ".tools\ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpegExe)) {
    Write-Host "  Dang tai FFmpeg..." -ForegroundColor Yellow
    $ffUrl = "https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-essentials_build.zip"
    $ffZip = Join-Path $env:TEMP "ffmpeg-package.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $ffUrl -OutFile $ffZip -TimeoutSec 600
    $stage = Join-Path $env:TEMP ("ffmpeg-" + [guid]::NewGuid().ToString("N"))
    Expand-Archive -LiteralPath $ffZip -DestinationPath $stage -Force
    $extracted = Get-ChildItem $stage -Directory | Select-Object -First 1
    $ffDest = Join-Path $Root ".tools\ffmpeg"
    New-Item -ItemType Directory -Path $ffDest -Force | Out-Null
    Copy-Item "$($extracted.FullName)\*" -Destination $ffDest -Recurse -Force
    Remove-Item $ffZip -ErrorAction SilentlyContinue
    Remove-Item $stage -Recurse -ErrorAction SilentlyContinue
}
Write-Host "  FFmpeg OK"

# -- 3. Tai PostgreSQL portable neu thieu -------------------------------------
Write-Host ""
Write-Host "[3/5] Kiem tra PostgreSQL portable..." -ForegroundColor Green
$pgCtl = Join-Path $Root ".tools\postgresql\pgsql\bin\pg_ctl.exe"
if (-not (Test-Path $pgCtl)) {
    Write-Host "  Dang tai PostgreSQL portable..." -ForegroundColor Yellow
    $pgUrl = "https://get.enterprisedb.com/postgresql/postgresql-17.5-1-windows-x64-binaries.zip"
    $pgZip = Join-Path $env:TEMP "postgresql-binaries.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $pgUrl -OutFile $pgZip -TimeoutSec 600
    $pgDest = Join-Path $Root ".tools\postgresql"
    New-Item -ItemType Directory -Path $pgDest -Force | Out-Null
    Expand-Archive -LiteralPath $pgZip -DestinationPath $pgDest -Force
    Remove-Item $pgZip -ErrorAction SilentlyContinue
}
Write-Host "  PostgreSQL OK"

# -- 4. Khoi tao database ----------------------------------------------------
Write-Host ""
Write-Host "[4/5] Khoi tao database..." -ForegroundColor Green
$pgData = Join-Path $Root "data\postgresql"
$env:Path = "$(Join-Path $Root '.tools\postgresql\pgsql\bin');$(Join-Path $Root '.tools\ffmpeg\bin');$env:Path"

if (-not (Test-Path (Join-Path $pgData "PG_VERSION"))) {
    Write-Host "  Tao cluster PostgreSQL..."
    New-Item -ItemType Directory -Path $pgData -Force | Out-Null

    $initdb = Join-Path $Root ".tools\postgresql\pgsql\bin\initdb.exe"
    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    $pgAdminPass = -join (1..20 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    $appPass = -join (1..20 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })

    $pwFile = Join-Path $env:TEMP "pg_init_pw.txt"
    Set-Content $pwFile $pgAdminPass -NoNewline
    & $initdb -D $pgData -U postgres -A md5 --pwfile=$pwFile --encoding=UTF8 --locale=C
    Remove-Item $pwFile -ErrorAction SilentlyContinue

    # Configure port
    $pgConf = Join-Path $pgData "postgresql.conf"
    Add-Content $pgConf "`nport = 55432`nlisten_addresses = '127.0.0.1'`nlog_destination = 'stderr'`nlogging_collector = off"

    # Start PostgreSQL
    $pgCtlExe = Join-Path $Root ".tools\postgresql\pgsql\bin\pg_ctl.exe"
    $logDir = Join-Path $Root "logs"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    & $pgCtlExe -D $pgData -l (Join-Path $logDir "postgresql.log") -w start
    Start-Sleep 2

    # Create user and database
    $psqlExe = Join-Path $Root ".tools\postgresql\pgsql\bin\psql.exe"
    $env:PGPASSWORD = $pgAdminPass
    $escapedPass = $appPass.Replace("'", "''")
    & $psqlExe -U postgres -h 127.0.0.1 -p 55432 -d postgres -c "CREATE ROLE video_tts_app LOGIN PASSWORD '$escapedPass'"
    & $psqlExe -U postgres -h 127.0.0.1 -p 55432 -d postgres -c "CREATE DATABASE video_tts_studio OWNER video_tts_app"
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

    # Write .env
    $encodedPass = [uri]::EscapeDataString($appPass)
    $envLines = @(
        "DATABASE_URL=postgresql+psycopg://video_tts_app:${encodedPass}@127.0.0.1:55432/video_tts_studio"
        "APP_HOST=127.0.0.1"
        "APP_PORT=8765"
        "DATA_DIR=./data"
        "LOG_DIR=./logs"
        "VIENEU_REPO=."
        "TTS_DEVICE=cpu"
        "TTS_PRELOAD=1"
        "MAX_SEQUENCE_OUTPUTS=100"
        "MAX_UPLOAD_MB=4096"
        "MAX_CONCURRENT_JOBS=4"
        "VIENEU_OFFLINE=1"
        "SKILLS_DIR=./skills"
        "AI_DEFAULT_PROVIDER=auto"
        "AI_TIMEOUT_SECONDS=30"
        "AI_MAX_RETRIES=1"
        "AI_COOLDOWN_SECONDS=60"
        "GEMINI_API_KEY="
        "GEMINI_MODEL="
        "GROQ_API_KEY="
        "GROQ_MODEL="
        "OPENROUTER_API_KEY="
        "OPENROUTER_MODEL="
    )
    $envText = $envLines -join "`n"
    [System.IO.File]::WriteAllText((Join-Path $Root ".env"), $envText, [System.Text.UTF8Encoding]::new($false))

    # Save credentials
    $credDir = Join-Path $Root "data\credentials"
    New-Item -ItemType Directory -Path $credDir -Force | Out-Null
    Set-Content (Join-Path $credDir "pg_admin_password.txt") $pgAdminPass
    Set-Content (Join-Path $credDir "app_password.txt") $appPass
    Write-Host "  Mat khau luu tai data\credentials\" -ForegroundColor Yellow
} else {
    Write-Host "  Database da ton tai, bo qua."
    if (-not (Test-Path (Join-Path $Root ".env"))) {
        throw "Database da co nhung thieu .env"
    }
}

# -- 5. Kiem tra model --------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Kiem tra TTS model cache..." -ForegroundColor Green
$hfHome = Join-Path $Root ".tools\huggingface"
$env:HF_HOME = $hfHome
$modelDir = Join-Path $hfHome "hub\models--pnnbao-ump--VieNeu-TTS-v3-Turbo"
if (Test-Path $modelDir) {
    Write-Host "  Model VieNeu-TTS v3 Turbo: OK"
} else {
    Write-Host "  Model chua co. Se tu tai khi chay TTS lan dau (~2 GB)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Cai dat hoan tat! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Khoi dong: chay start.bat" -ForegroundColor Cyan
Write-Host "Truy cap:  http://127.0.0.1:8765" -ForegroundColor Cyan
Write-Host ""

Pop-Location