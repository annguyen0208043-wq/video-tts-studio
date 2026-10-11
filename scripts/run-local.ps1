$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "..\VieNeu-TTS\.venv\Scripts\python.exe"
$FrontendDist = Join-Path $ProjectRoot "frontend\dist\index.html"

if (-not (Test-Path $Python)) {
    throw "Không tìm thấy môi trường VieNeu-TTS: $Python"
}
if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    throw "Thiếu .env. Hãy copy .env.example thành .env và điền mật khẩu PostgreSQL."
}
if (-not (Test-Path $FrontendDist)) {
    Write-Host "Frontend chưa build. Đang chạy npm build..." -ForegroundColor Cyan
    & npm.cmd --prefix (Join-Path $ProjectRoot "frontend") run build
}

Push-Location (Join-Path $ProjectRoot "backend")
try {
    & $Python -m alembic upgrade head
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
} finally {
    Pop-Location
}

