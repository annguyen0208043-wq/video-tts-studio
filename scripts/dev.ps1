$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:Path = "$ProjectRoot\.tools\node;$ProjectRoot\.tools\ffmpeg\bin;" + $env:Path
$env:HF_HOME = Join-Path $ProjectRoot '.tools\huggingface'
$Python = Join-Path $ProjectRoot "..\VieNeu-TTS\.venv\Scripts\python.exe"
if (Test-Path "$ProjectRoot\.venv\Scripts\python.exe") { $Python = "$ProjectRoot\.venv\Scripts\python.exe" }
$BackendDir = Join-Path $ProjectRoot "backend"

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    throw "Thiếu .env. Hãy copy .env.example thành .env và điền mật khẩu PostgreSQL."
}

& $Python (Join-Path $PSScriptRoot 'start_local_postgres.py')
if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL startup failed.' }
Start-Process -FilePath $Python -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8765" -WorkingDirectory $BackendDir -WindowStyle Hidden
& npm.cmd --prefix (Join-Path $ProjectRoot "frontend") run dev

