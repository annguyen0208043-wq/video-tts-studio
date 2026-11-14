<#
.SYNOPSIS
    Dong goi Video TTS Studio thanh ban phan phoi offline cho may moi.
.DESCRIPTION
    Script tao thu muc phan phoi chua moi thu can thiet de may Windows moi
    (khong can cai them gi) co the chay Video TTS Studio ngay.
.PARAMETER OutputDir
    Thu muc chua ban dong goi. Mac dinh: .\dist-package
.PARAMETER IncludeGPU
    Them ca PyTorch CUDA. Mac dinh chi CPU/ONNX.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1
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
if ($IncludeGPU) { Write-Host "Mode: CPU + GPU (CUDA)" } else { Write-Host "Mode: CPU only (ONNX)" }
Write-Host ""

# -- 0. Kiem tra dieu kien ---------------------------------------------------
$VieNeuRoot = Join-Path $ProjectRoot "..\VieNeu-TTS"
if (-not (Test-Path (Join-Path $VieNeuRoot "pyproject.toml"))) {
    throw "Khong tim thay VieNeu-TTS tai $VieNeuRoot"
}
$SourcePython = Join-Path $VieNeuRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $SourcePython)) {
    $alt = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $alt) { $SourcePython = $alt } else { throw "Khong tim thay moi truong Python." }
}

# -- 1. Tao thu muc dich -----------------------------------------------------
if (Test-Path $Dist) {
    Write-Host "Xoa thu muc cu: $Dist" -ForegroundColor Yellow
    Remove-Item $Dist -Recurse -Force
}
New-Item -ItemType Directory -Path $Dist -Force | Out-Null

# -- 2. Copy source code -----------------------------------------------------
Write-Host "[1/8] Copy ma nguon..." -ForegroundColor Green

$skipDirs = @('.git', '.tmp', '.uv-cache', '.pytest_cache', '__pycache__',
    'node_modules', 'test-final-data', 'test-final-audit-data',
    'test-full-optimize-data', 'test-optimize-data', 'test-optimize-2-data',
    'development_logs', '.venv', '.tools', 'dist-package')
$skipFiles = @('.env', 'run.txt', '*.log', '*.sqlite3', '*.tsbuildinfo',
    'vite.config.js', 'vite.config.d.ts')

function Copy-Tree {
    param([string]$Src, [string]$Dst)
    Get-ChildItem $Src -Force | ForEach-Object {
        if ($_.PSIsContainer) {
            $n = $_.Name
            if ($n -notin $skipDirs -and $n -notmatch '^test-.*-data$') {
                $sub = Join-Path $Dst $n
                New-Item -ItemType Directory -Path $sub -Force | Out-Null
                Copy-Tree -Src $_.FullName -Dst $sub
            }
        } else {
            $matched = $false
            foreach ($pat in $skipFiles) { if ($_.Name -like $pat) { $matched = $true; break } }
            if (-not $matched) {
                Copy-Item $_.FullName -Destination (Join-Path $Dst $_.Name) -Force
            }
        }
    }
}
Copy-Tree -Src $ProjectRoot -Dst $Dist

# -- 3. Build frontend -------------------------------------------------------
Write-Host "[2/8] Build frontend..." -ForegroundColor Green
$frontendIndex = Join-Path $ProjectRoot "frontend\dist\index.html"
if (-not (Test-Path $frontendIndex)) {
    Push-Location (Join-Path $ProjectRoot "frontend")
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "npm build failed" }
    Pop-Location
}
$distFE = Join-Path $Dist "frontend\dist"
New-Item -ItemType Directory -Path $distFE -Force | Out-Null
Copy-Item (Join-Path $ProjectRoot "frontend\dist\*") -Destination $distFE -Recurse -Force

# -- 4. Python embeddable ----------------------------------------------------
Write-Host "[3/8] Tai Python embeddable..." -ForegroundColor Green
# Use 3.12.10 which is the latest 3.12.x with an embeddable package
$PyVer = "3.12.10"
$PyEmbed = Join-Path $Dist ".python"
$PyZipUrl = "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip"
$PyZipFile = Join-Path $env:TEMP "python-embed-$PyVer.zip"

if (-not (Test-Path $PyZipFile)) {
    Write-Host "  Downloading Python $PyVer embedded..."
    Invoke-WebRequest -UseBasicParsing -Uri $PyZipUrl -OutFile $PyZipFile -TimeoutSec 300
}
Expand-Archive -LiteralPath $PyZipFile -DestinationPath $PyEmbed -Force

# Enable site-packages in embedded Python
$pthFile = Get-ChildItem $PyEmbed -Filter "python31*._pth" | Select-Object -First 1
if (-not $pthFile) { $pthFile = Get-ChildItem $PyEmbed -Filter "python*._pth" | Select-Object -First 1 }
if ($pthFile) {
    $lines = Get-Content $pthFile.FullName
    $lines = $lines -replace '^#import site', 'import site'
    $lines += "Lib\site-packages"
    Set-Content $pthFile.FullName $lines -Encoding ASCII
    Write-Host "  Patched $($pthFile.Name) for site-packages"
}

# -- 5. Install pip + packages ------------------------------------------------
Write-Host "[4/8] Cai Python packages..." -ForegroundColor Green
$EmbedPy = Join-Path $PyEmbed "python.exe"
$SitePkg = Join-Path $PyEmbed "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePkg -Force | Out-Null

# get-pip
$getPip = Join-Path $env:TEMP "get-pip.py"
if (-not (Test-Path $getPip)) {
    Write-Host "  Downloading get-pip.py..."
    Invoke-WebRequest -UseBasicParsing -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -TimeoutSec 120
}
Write-Host "  Installing pip..."
& $EmbedPy $getPip --no-warn-script-location 2>&1 | Select-Object -Last 3

# VieNeu-TTS CPU
Write-Host "  Installing VieNeu-TTS (CPU/ONNX)..."
& $EmbedPy -m pip install --no-warn-script-location "vieneu==3.8.3"
if ($LASTEXITCODE -ne 0) { throw "Failed to install vieneu" }

if ($IncludeGPU) {
    Write-Host "  Installing PyTorch CUDA..."
    & $EmbedPy -m pip install --no-warn-script-location torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
    & $EmbedPy -m pip install --no-warn-script-location transformers safetensors
}

# Backend requirements (skip vieneu, already installed)
Write-Host "  Installing backend requirements..."
$reqFile = Join-Path $Dist "backend\requirements.txt"
$tempReq = Join-Path $env:TEMP "backend-req-filtered.txt"
Get-Content $reqFile | Where-Object { $_ -notmatch '^vieneu' } | Set-Content $tempReq
& $EmbedPy -m pip install --no-warn-script-location -r $tempReq
if ($LASTEXITCODE -ne 0) { throw "Failed to install backend requirements" }

# -- 6. Copy model cache -----------------------------------------------------
Write-Host "[5/8] Copy model cache HuggingFace (~2 GB)..." -ForegroundColor Green
$srcHF = Join-Path $ProjectRoot ".tools\huggingface"
$dstHF = Join-Path $Dist ".tools\huggingface"
if (Test-Path $srcHF) {
    New-Item -ItemType Directory -Path (Split-Path $dstHF) -Force | Out-Null
    & robocopy $srcHF $dstHF /E /NFL /NDL /NJH /NJS /NP | Out-Null
    Write-Host "  Done"
} else {
    Write-Host "  WARNING: Cache not found. Model se duoc tai khi chay lan dau." -ForegroundColor Yellow
}

# -- 7. Copy FFmpeg -----------------------------------------------------------
Write-Host "[6/8] Copy FFmpeg..." -ForegroundColor Green
$srcFF = Join-Path $ProjectRoot ".tools\ffmpeg"
$dstFF = Join-Path $Dist ".tools\ffmpeg"
if (Test-Path $srcFF) {
    New-Item -ItemType Directory -Path $dstFF -Force | Out-Null
    & robocopy $srcFF $dstFF /E /NFL /NDL /NJH /NJS /NP | Out-Null
    Write-Host "  Done"
} else {
    Write-Host "  WARNING: FFmpeg not found. Se tai khi cai dat." -ForegroundColor Yellow
}

# -- 8. Copy PostgreSQL portable ----------------------------------------------
Write-Host "[7/8] Copy PostgreSQL portable..." -ForegroundColor Green
$srcPG = Join-Path $ProjectRoot ".tools\postgresql"
$dstPG = Join-Path $Dist ".tools\postgresql"
if (Test-Path $srcPG) {
    New-Item -ItemType Directory -Path $dstPG -Force | Out-Null
    & robocopy $srcPG $dstPG /E /NFL /NDL /NJH /NJS /NP | Out-Null
    Write-Host "  Done"
} else {
    Write-Host "  WARNING: PostgreSQL not found. Se tai khi cai dat." -ForegroundColor Yellow
}

# -- 9. Create launchers for target machine -----------------------------------
Write-Host "[8/8] Tao scripts cho may dich..." -ForegroundColor Green

# install.bat
@"
@echo off
setlocal
cd /d "%~dp0"
title Video TTS Studio - First-Time Setup
echo ============================================
echo   Video TTS Studio - Cai Dat Lan Dau
echo ============================================
echo.
if exist "data\postgresql\PG_VERSION" (
    echo Da cai dat truoc do. Chay start.bat de khoi dong.
    pause
    exit /b 0
)
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
"@ | Set-Content (Join-Path $Dist "install.bat") -Encoding ASCII

# start.bat
@"
@echo off
setlocal
cd /d "%~dp0"
title Video TTS Studio
set "PATH=%~dp0.python;%~dp0.python\Scripts;%~dp0.tools\ffmpeg\bin;%~dp0.tools\postgresql\pgsql\bin;%PATH%"
set "PYTHONPATH=%~dp0.python\Lib\site-packages"
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
"%PYTHON%" scripts\start_local_postgres.py 2>nul
cd /d "%~dp0backend"
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Database migration that bai.
    pause
    exit /b 1
)
echo.
echo Mo http://127.0.0.1:8765 trong trinh duyet.
echo Nhan Ctrl+C de dung server.
echo.
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
if errorlevel 1 (
    echo Server da dung hoac gap loi.
    pause
)
"@ | Set-Content (Join-Path $Dist "start.bat") -Encoding ASCII

# -- Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "=== Dong goi hoan tat ===" -ForegroundColor Green
$totalBytes = (Get-ChildItem $Dist -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Write-Host "Thu muc: $Dist"
Write-Host ("Kich thuoc: {0:N2} GB" -f ($totalBytes / 1GB))
Write-Host ""
Write-Host "Buoc tiep theo:" -ForegroundColor Cyan
Write-Host "  1. Nen thu muc dist-package thanh .zip hoac .7z"
Write-Host "  2. Gui file nen cho may dich"
Write-Host "  3. Giai nen va chay install.bat"
Write-Host "  4. Sau do chay start.bat de khoi dong"