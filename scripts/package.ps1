<#
.SYNOPSIS
    Đóng gói Video TTS Studio thành bản phân phối offline cho máy mới.

.DESCRIPTION
    Script tạo thư mục phân phối chứa mọi thứ cần thiết để máy Windows mới
    (không cần cài thêm gì) có thể chạy Video TTS Studio ngay:
      - Python embedded 3.12
      - Tất cả packages Python (VieNeu-TTS + backend deps)
      - HuggingFace model cache (ONNX)
      - FFmpeg + FFprobe
      - PostgreSQL portable
      - Frontend đã build sẵn
      - Script install.bat một-click cho máy đích

.PARAMETER OutputDir
    Thư mục chứa bản đóng gói. Mặc định: .\dist-package

.PARAMETER IncludeGPU
    Thêm cả PyTorch CUDA (tăng ~5 GB). Mặc định chỉ CPU/ONNX.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1 -IncludeGPU
#>
param(
    [string]$OutputDir = ".\dist-package",
    [switch]$IncludeGPU
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $ProjectRoot $OutputDir

Write-Host "=== Video TTS Studio Packager ===" -ForegroundColor Cyan
Write-Host "Output: $Dist"
Write-Host "Mode: $(if ($IncludeGPU) { 'CPU + GPU (CUDA)' } else { 'CPU only (ONNX)' })"
Write-Host ""

# ── 0. Kiểm tra điều kiện ──────────────────────────────────────────────
$VieNeuRoot = Join-Path $ProjectRoot "..\VieNeu-TTS"
if (-not (Test-Path (Join-Path $VieNeuRoot "pyproject.toml"))) {
    throw "Không tìm thấy VieNeu-TTS tại $VieNeuRoot. Đặt nó cạnh video-tts-studio."
}
$SourcePython = Join-Path $VieNeuRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $SourcePython)) {
    if (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe")) {
        $SourcePython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    } else {
        throw "Không tìm thấy môi trường Python."
    }
}

# ── 1. Tạo thư mục đích ────────────────────────────────────────────────
if (Test-Path $Dist) {
    Write-Host "Xóa thư mục cũ: $Dist" -ForegroundColor Yellow
    Remove-Item $Dist -Recurse -Force
}
New-Item -ItemType Directory -Path $Dist -Force | Out-Null

# ── 2. Copy source code (không bao gồm data/test lớn) ──────────────────
Write-Host "[1/8] Copy mã nguồn..." -ForegroundColor Green
$excludeDirs = @('.git', '.tmp', '.uv-cache', '.pytest_cache', '__pycache__',
    'node_modules', 'test-final-data', 'test-final-audit-data',
    'test-full-optimize-data', 'test-optimize-data', 'test-optimize-2-data',
    'development_logs', '.venv', '.tools')
$excludeFiles = @('.env', 'run.txt', '*.log', '*.sqlite3', '*.tsbuildinfo',
    'vite.config.js', 'vite.config.d.ts')

function Copy-ProjectTree($Source, $Destination, $ExcludeDirs, $ExcludeFiles) {
    Get-ChildItem $Source -Force | ForEach-Object {
        $name = $_.Name
        if ($_.PSIsContainer) {
            if ($name -notin $ExcludeDirs -and $name -notmatch '^test-.*-data$') {
                $destSub = Join-Path $Destination $name
                New-Item -ItemType Directory -Path $destSub -Force | Out-Null
                Copy-ProjectTree $_.FullName $destSub $ExcludeDirs $ExcludeFiles
            }
        } else {
            $skip = $false
            foreach ($pattern in $ExcludeFiles) {
                if ($name -like $pattern) { $skip = $true; break }
            }
            if (-not $skip) {
                Copy-Item $_.FullName -Destination (Join-Path $Destination $name) -Force
            }
        }
    }
}
Copy-ProjectTree $ProjectRoot $Dist $excludeDirs $excludeFiles

# ── 3. Build frontend ──────────────────────────────────────────────────
Write-Host "[2/8] Build frontend..." -ForegroundColor Green
$frontendDist = Join-Path $ProjectRoot "frontend\dist\index.html"
if (-not (Test-Path $frontendDist)) {
    Push-Location (Join-Path $ProjectRoot "frontend")
    & npm.cmd install
    & npm.cmd run build
    Pop-Location
}
$distFrontend = Join-Path $Dist "frontend\dist"
New-Item -ItemType Directory -Path $distFrontend -Force | Out-Null
Copy-Item (Join-Path $ProjectRoot "frontend\dist\*") -Destination $distFrontend -Recurse -Force

# ── 4. Tải Python embeddable ───────────────────────────────────────────
Write-Host "[3/8] Tải Python embeddable..." -ForegroundColor Green
$PyVersion = & $SourcePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
$PyEmbed = Join-Path $Dist ".python"
$PyZipUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$PyZipFile = Join-Path $env:TEMP "python-embed-$PyVersion.zip"

if (-not (Test-Path $PyZipFile)) {
    Write-Host "  Downloading Python $PyVersion embedded..."
    Invoke-WebRequest -UseBasicParsing -Uri $PyZipUrl -OutFile $PyZipFile -TimeoutSec 300
}
Expand-Archive -LiteralPath $PyZipFile -DestinationPath $PyEmbed -Force

# Enable pip/site-packages in embedded Python
$pthFile = Get-ChildItem $PyEmbed -Filter "python*._pth" | Select-Object -First 1
if ($pthFile) {
    $content = Get-Content $pthFile.FullName
    $content = $content -replace '#import site', 'import site'
    # Add Lib\site-packages
    $content += "`nLib\site-packages"
    Set-Content $pthFile.FullName $content
}

# ── 5. Cài packages vào embedded Python ────────────────────────────────
Write-Host "[4/8] Cài Python packages..." -ForegroundColor Green
$EmbedPython = Join-Path $PyEmbed "python.exe"
$SitePackages = Join-Path $PyEmbed "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null

# Install pip first
Write-Host "  Installing pip..."
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipFile = Join-Path $env:TEMP "get-pip.py"
if (-not (Test-Path $getPipFile)) {
    Invoke-WebRequest -UseBasicParsing -Uri $getPipUrl -OutFile $getPipFile -TimeoutSec 120
}
& $EmbedPython $getPipFile --no-warn-script-location

# Install VieNeu-TTS (CPU only, no torch)
Write-Host "  Installing VieNeu-TTS (CPU/ONNX)..."
& $EmbedPython -m pip install --no-warn-script-location `
    "vieneu==3.8.3" --target $SitePackages

if ($IncludeGPU) {
    Write-Host "  Installing PyTorch CUDA..."
    & $EmbedPython -m pip install --no-warn-script-location `
        torch==2.8.0 torchaudio==2.8.0 `
        --index-url https://download.pytorch.org/whl/cu128 `
        --target $SitePackages
    & $EmbedPython -m pip install --no-warn-script-location `
        transformers safetensors `
        --target $SitePackages
} else {
    Write-Host "  Skipping PyTorch CUDA (CPU-only mode)"
}

# Install backend requirements
Write-Host "  Installing backend requirements..."
& $EmbedPython -m pip install --no-warn-script-location `
    -r (Join-Path $Dist "backend\requirements.txt") `
    --target $SitePackages

# ── 6. Copy model cache ───────────────────────────────────────────────
Write-Host "[5/8] Copy model cache HuggingFace (~2 GB)..." -ForegroundColor Green
$sourceHF = Join-Path $ProjectRoot ".tools\huggingface"
$destHF = Join-Path $Dist ".tools\huggingface"
if (Test-Path $sourceHF) {
    New-Item -ItemType Directory -Path (Join-Path $Dist ".tools") -Force | Out-Null
    & robocopy $sourceHF $destHF /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    Write-Host "  WARNING: Model cache not found at $sourceHF" -ForegroundColor Yellow
    Write-Host "  Ứng dụng sẽ tải model khi chạy lần đầu (~2 GB)" -ForegroundColor Yellow
}

# ── 7. Copy/tải FFmpeg ─────────────────────────────────────────────────
Write-Host "[6/8] Copy FFmpeg..." -ForegroundColor Green
$sourceFFmpeg = Join-Path $ProjectRoot ".tools\ffmpeg"
$destFFmpeg = Join-Path $Dist ".tools\ffmpeg"
if (Test-Path $sourceFFmpeg) {
    New-Item -ItemType Directory -Path $destFFmpeg -Force | Out-Null
    & robocopy $sourceFFmpeg $destFFmpeg /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    Write-Host "  FFmpeg sẽ được tải khi cài đặt" -ForegroundColor Yellow
}

# ── 8. Copy/tải PostgreSQL portable ───────────────────────────────────
Write-Host "[7/8] Copy PostgreSQL portable..." -ForegroundColor Green
$sourcePG = Join-Path $ProjectRoot ".tools\postgresql"
$destPG = Join-Path $Dist ".tools\postgresql"
if (Test-Path $sourcePG) {
    New-Item -ItemType Directory -Path $destPG -Force | Out-Null
    & robocopy $sourcePG $destPG /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    Write-Host "  PostgreSQL portable sẽ được tải khi cài đặt" -ForegroundColor Yellow
}

# ── 9. Tạo script cài đặt và khởi chạy cho máy đích ──────────────────
Write-Host "[8/8] Tạo scripts cho máy đích..." -ForegroundColor Green

# install.bat - one-click installer
$installBat = @'
@echo off
setlocal
cd /d "%~dp0"
title Video TTS Studio - First-Time Setup
echo ============================================
echo   Video TTS Studio - Cai Dat Lan Dau
echo ============================================
echo.

:: Check if already installed
if exist "data\postgresql\PG_VERSION" (
    echo Da cai dat truoc do. Chay start.bat de khoi dong.
    pause
    exit /b 0
)

:: Run PowerShell installer
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\first-setup.ps1"
if errorlevel 1 (
    echo.
    echo Cai dat that bai. Xem loi phia tren.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Cai dat hoan tat!
echo   Chay start.bat de khoi dong ung dung.
echo ============================================
pause
'@
Set-Content (Join-Path $Dist "install.bat") $installBat -Encoding ASCII

# start.bat - launcher for installed app
$startBat = @'
@echo off
setlocal
cd /d "%~dp0"
title Video TTS Studio
set "PATH=%~dp0.python;%~dp0.python\Scripts;%~dp0.tools\ffmpeg\bin;%~dp0.tools\postgresql\pgsql\bin;%PATH%"
set "PYTHONPATH=%~dp0.python\Lib\site-packages;%~dp0backend"
set "HF_HOME=%~dp0.tools\huggingface"
set "PYTHON=%~dp0.python\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Chua cai dat. Chay install.bat truoc.
    pause
    exit /b 1
)
if not exist ".env" (
    echo [ERROR] Thieu .env. Chay install.bat truoc.
    pause
    exit /b 1
)

:: Start PostgreSQL if using local instance
"%PYTHON%" scripts\start_local_postgres.py 2>nul

:: Run migrations
cd /d "%~dp0backend"
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Database migration that bai.
    pause
    exit /b 1
)

echo.
echo Mo http://127.0.0.1:8765 trong trinh duyet sau khi server khoi dong.
echo Nhan Ctrl+C de dung server.
echo.
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
if errorlevel 1 (
    echo.
    echo Server da dung hoac gap loi.
    pause
)
exit /b 0
'@
Set-Content (Join-Path $Dist "start.bat") $startBat -Encoding ASCII

# first-setup.ps1 - detailed installer
$firstSetupContent = @'
<#
.SYNOPSIS
    First-time setup for Video TTS Studio on a new Windows machine.
    Run via install.bat or: powershell -ExecutionPolicy Bypass -File .\scripts\first-setup.ps1
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root

Write-Host "=== Video TTS Studio - Cai Dat ===" -ForegroundColor Cyan

# ── 1. Kiểm tra Python embedded ────────────────────────────────────────
Write-Host ""
Write-Host "[1/5] Kiem tra Python..." -ForegroundColor Green
$Python = Join-Path $Root ".python\python.exe"
if (-not (Test-Path $Python)) {
    throw "Thieu .python\python.exe. Ban phan phoi bi hong."
}
& $Python -c "import sys; print(f'  Python {sys.version}')"

# ── 2. Tải FFmpeg nếu thiếu ────────────────────────────────────────────
Write-Host ""
Write-Host "[2/5] Kiem tra FFmpeg..." -ForegroundColor Green
$ffmpegExe = Join-Path $Root ".tools\ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpegExe)) {
    Write-Host "  Dang tai FFmpeg..." -ForegroundColor Yellow
    $ffmpegUrl = "https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-essentials_build.zip"
    $ffmpegZip = Join-Path $env:TEMP "ffmpeg-package.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $ffmpegUrl -OutFile $ffmpegZip -TimeoutSec 600
    $stage = Join-Path $env:TEMP "ffmpeg-extract"
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $stage -Force
    $source = Get-ChildItem $stage -Directory | Select-Object -First 1
    $dest = Join-Path $Root ".tools\ffmpeg"
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Copy-Item "$($source.FullName)\*" -Destination $dest -Recurse -Force
    Remove-Item $ffmpegZip -ErrorAction SilentlyContinue
    Remove-Item $stage -Recurse -ErrorAction SilentlyContinue
}
Write-Host "  FFmpeg OK"

# ── 3. Tải PostgreSQL portable nếu thiếu ──────────────────────────────
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

# ── 4. Khởi tạo database ──────────────────────────────────────────────
Write-Host ""
Write-Host "[4/5] Khoi tao database..." -ForegroundColor Green
$pgData = Join-Path $Root "data\postgresql"
$env:Path = "$(Join-Path $Root '.tools\postgresql\pgsql\bin');$(Join-Path $Root '.tools\ffmpeg\bin');$env:Path"

if (-not (Test-Path (Join-Path $pgData "PG_VERSION"))) {
    Write-Host "  Tao cluster PostgreSQL..."
    New-Item -ItemType Directory -Path $pgData -Force | Out-Null

    $initdb = Join-Path $Root ".tools\postgresql\pgsql\bin\initdb.exe"
    # Tạo password tự động
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%'
    $pgAdminPass = -join (1..20 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    $appPass = -join (1..20 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })

    $pwFile = Join-Path $env:TEMP "pg_init_pw.txt"
    Set-Content $pwFile $pgAdminPass -NoNewline
    & $initdb -D $pgData -U postgres -A md5 --pwfile=$pwFile --encoding=UTF8 --locale=C
    Remove-Item $pwFile -ErrorAction SilentlyContinue

    # Cấu hình port
    $pgConf = Join-Path $pgData "postgresql.conf"
    Add-Content $pgConf "`nport = 55432`nlisten_addresses = '127.0.0.1'`nlog_destination = 'stderr'`nlogging_collector = off"

    # Khởi động PostgreSQL
    $pgCtlExe = Join-Path $Root ".tools\postgresql\pgsql\bin\pg_ctl.exe"
    $logDir = Join-Path $Root "logs"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    & $pgCtlExe -D $pgData -l (Join-Path $logDir "postgresql.log") -w start
    Start-Sleep 2

    # Tạo user và database
    $psqlExe = Join-Path $Root ".tools\postgresql\pgsql\bin\psql.exe"
    $env:PGPASSWORD = $pgAdminPass
    $escapedAppPass = $appPass.Replace("'", "''")
    & $psqlExe -U postgres -h 127.0.0.1 -p 55432 -d postgres -c "CREATE ROLE video_tts_app LOGIN PASSWORD '$escapedAppPass'"
    & $psqlExe -U postgres -h 127.0.0.1 -p 55432 -d postgres -c "CREATE DATABASE video_tts_studio OWNER video_tts_app"
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

    # Ghi .env
    $encodedPass = [uri]::EscapeDataString($appPass)
    $envContent = @"
DATABASE_URL=postgresql+psycopg://video_tts_app:$encodedPass@127.0.0.1:55432/video_tts_studio
APP_HOST=127.0.0.1
APP_PORT=8765
DATA_DIR=./data
LOG_DIR=./logs
VIENEU_REPO=.
TTS_DEVICE=cpu
TTS_PRELOAD=1
MAX_SEQUENCE_OUTPUTS=100
MAX_UPLOAD_MB=4096
MAX_CONCURRENT_JOBS=4
VIENEU_OFFLINE=1
SKILLS_DIR=./skills
AI_DEFAULT_PROVIDER=auto
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=1
AI_COOLDOWN_SECONDS=60
GEMINI_API_KEY=
GEMINI_MODEL=
GROQ_API_KEY=
GROQ_MODEL=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
"@
    [System.IO.File]::WriteAllText((Join-Path $Root ".env"), $envContent, [System.Text.UTF8Encoding]::new($false))

    # Lưu admin password
    $credDir = Join-Path $Root "data\credentials"
    New-Item -ItemType Directory -Path $credDir -Force | Out-Null
    Set-Content (Join-Path $credDir "pg_admin_password.txt") $pgAdminPass
    Set-Content (Join-Path $credDir "app_password.txt") $appPass
    Write-Host "  Mat khau PostgreSQL da luu tai data\credentials\" -ForegroundColor Yellow
} else {
    Write-Host "  Database da ton tai, bo qua."
    if (-not (Test-Path (Join-Path $Root ".env"))) {
        throw "Database da co nhung thieu .env. Kiem tra lai."
    }
}

# ── 5. Tải model nếu thiếu ────────────────────────────────────────────
Write-Host ""
Write-Host "[5/5] Kiem tra TTS model cache..." -ForegroundColor Green
$hfHome = Join-Path $Root ".tools\huggingface"
$env:HF_HOME = $hfHome
$modelCheck = Join-Path $hfHome "hub\models--pnnbao-ump--VieNeu-TTS-v3-Turbo"
if (Test-Path $modelCheck) {
    Write-Host "  Model VieNeu-TTS v3 Turbo: OK"
} else {
    Write-Host "  Model chua co. Se tu tai khi chay TTS lan dau (~2 GB)." -ForegroundColor Yellow
    Write-Host "  Hoac chay thu: .python\python.exe -c `"from vieneu import Vieneu; v = Vieneu(device='cpu', backend='onnx'); print('OK')`"" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Cai dat hoan tat! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Khoi dong: chay start.bat" -ForegroundColor Cyan
Write-Host "Truy cap:  http://127.0.0.1:8765" -ForegroundColor Cyan
Write-Host ""

Pop-Location
'@
$setupScriptDir = Join-Path $Dist "scripts"
if (-not (Test-Path $setupScriptDir)) { New-Item -ItemType Directory -Path $setupScriptDir -Force | Out-Null }
Set-Content (Join-Path $setupScriptDir "first-setup.ps1") $firstSetupContent -Encoding UTF8

# ── 10. Tính kích thước ───────────────────────────────────────────────
Write-Host ""
Write-Host "=== Đóng gói hoàn tất ===" -ForegroundColor Green
$totalSize = (Get-ChildItem $Dist -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
Write-Host "Thư mục: $Dist"
Write-Host "Kích thước: $([math]::Round($totalSize / 1GB, 2)) GB"
Write-Host ""
Write-Host "Bước tiếp theo:" -ForegroundColor Cyan
Write-Host "  1. Nén thư mục '$OutputDir' thành .zip hoặc .7z"
Write-Host "  2. Gửi file nén cho máy đích"
Write-Host "  3. Giải nén và chạy install.bat"
Write-Host "  4. Sau đó chạy start.bat để khởi động"
Write-Host ""
