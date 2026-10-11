$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "..\VieNeu-TTS\.venv\Scripts\python.exe"
$BackendDir = Join-Path $ProjectRoot "backend"

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    throw "Thiếu .env. Hãy copy .env.example thành .env và điền mật khẩu PostgreSQL."
}

Start-Process -FilePath $Python -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8765" -WorkingDirectory $BackendDir -WindowStyle Hidden
& npm.cmd --prefix (Join-Path $ProjectRoot "frontend") run dev

