$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root '.tools'
New-Item -ItemType Directory -Path $tools -Force | Out-Null

function Install-ZipTool($Url, $Name, $Executable) {
    $destination = Join-Path $tools $Name
    if (Test-Path (Join-Path $destination $Executable)) { return }
    $archive = Join-Path $tools "$Name.zip"
    $stage = Join-Path $tools ($Name + '-' + [guid]::NewGuid().ToString('N'))
    Write-Host "Downloading $Name..."
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $archive -TimeoutSec 600
    Expand-Archive -LiteralPath $archive -DestinationPath $stage
    $source = Get-ChildItem -LiteralPath $stage -Directory | Select-Object -First 1
    if (-not $source -or -not (Test-Path (Join-Path $source.FullName $Executable))) {
        throw "Invalid archive for $Name"
    }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath $source.FullName -Force | Copy-Item -Destination $destination -Recurse -Force
    Remove-Item -LiteralPath $archive
}

$releases = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -TimeoutSec 60
$release = $releases | Where-Object { $_.lts -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
if (-not $release) { throw 'No Node.js LTS Windows x64 release found.' }
Install-ZipTool "https://nodejs.org/dist/$($release.version)/node-$($release.version)-win-x64.zip" 'node' 'node.exe'
Install-ZipTool 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' 'ffmpeg' 'bin\ffmpeg.exe'
$env:Path = "$tools\node;$tools\ffmpeg\bin;" + $env:Path
& node --version
& npm.cmd --version
& ffmpeg -version | Select-Object -First 1
& ffprobe -version | Select-Object -First 1
Write-Host 'Tools installed. run.bat will use them automatically.'
