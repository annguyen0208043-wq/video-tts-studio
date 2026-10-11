$ErrorActionPreference = "Stop"
$Connection = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Connection) {
    Write-Host "Video TTS Studio is not running on port 8765."
    exit 0
}

$ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($Connection.OwningProcess)"
if (-not $ProcessInfo -or $ProcessInfo.CommandLine -notmatch "uvicorn" -or $ProcessInfo.CommandLine -notmatch "8765") {
    throw "Port 8765 belongs to another process. It was not stopped."
}

Stop-Process -Id $Connection.OwningProcess
Write-Host "Video TTS Studio was stopped." -ForegroundColor Green
