$ErrorActionPreference = "Continue"
Write-Host "Video TTS Studio - Environment Check" -ForegroundColor Cyan
Write-Host "FFmpeg:"; ffmpeg -version | Select-Object -First 1
Write-Host "FFprobe:"; ffprobe -version | Select-Object -First 1
Write-Host "PostgreSQL:"; psql --version
Write-Host "PostgreSQL service:"; Get-Service -Name "*postgres*" | Format-Table Name,Status,StartType
Write-Host "NVIDIA:"; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "..\VieNeu-TTS\.venv\Scripts\python.exe"
Write-Host "VieNeu Python:"; & $Python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

