. "$PSScriptRoot\common.ps1"

$CampusTraceCloudflaredRoot = Join-Path $CampusTraceRoot "tools\cloudflared"
$CampusTraceCloudflared = Join-Path $CampusTraceCloudflaredRoot "cloudflared.exe"
$CampusTraceCloudflaredUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

if (-not (Test-Path -LiteralPath $CampusTracePython)) {
    throw "Python virtual environment is missing. Run scripts\setup.cmd first."
}

Write-Host "Installing locked Python dependencies..."
& $CampusTracePython -m pip install --requirement (Join-Path $CampusTraceBackend "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

if (-not (Test-Path -LiteralPath $CampusTraceCloudflared)) {
    New-Item -ItemType Directory -Force -Path $CampusTraceCloudflaredRoot | Out-Null
    Write-Host "Downloading cloudflared from Cloudflare's official GitHub release..."
    Invoke-WebRequest -Uri $CampusTraceCloudflaredUrl -OutFile $CampusTraceCloudflared -UseBasicParsing
}

& $CampusTraceCloudflared --version
if ($LASTEXITCODE -ne 0) { throw "cloudflared validation failed." }
Write-Host "Public test dependencies are ready."
