. "$PSScriptRoot\common.ps1"

# Launch every runtime through the ASCII-only junction so Windows PowerShell 5.1 is reliable.
Mount-CampusTraceRuntime
Start-CampusTraceMySql
if (Test-Path -LiteralPath (Join-Path $CampusTraceRoot 'tools\ollama\ollama.exe')) {
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-local-ai.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Local AI startup failed.' }
}
New-Item -ItemType Directory -Force -Path $CampusTraceLogRoot | Out-Null

# 每次启动都以幂等方式补齐数据库结构，确保拉取新代码后
# 仍然可以直接双击 start，不会因遗漏手动 migrate 而在提交时报错。
Push-Location $CampusTraceBackend
try { & $CampusTracePython manage.py migrate --noinput }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Database migration failed. Inspect the message above." }

if ((Get-CampusTraceListenerPid -Port 8000) -or (Get-CampusTraceListenerPid -Port 5173)) {
    throw "Django or Vite port is already in use. Run scripts\stop.cmd, then start again."
}

Start-Process -FilePath $CampusTracePython `
    -ArgumentList "manage.py", "runserver", "127.0.0.1:8000", "--noreload" `
    -WorkingDirectory $CampusTraceBackend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $CampusTraceLogRoot "backend.stdout.log") `
    -RedirectStandardError (Join-Path $CampusTraceLogRoot "backend.stderr.log") | Out-Null
$CampusTraceBackendPid = Wait-CampusTraceListener -Port 8000
if (-not $CampusTraceBackendPid) { throw "Django startup timed out. Inspect artifacts\logs\backend.stderr.log." }
$CampusTraceBackendPid | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot "backend.pid")

$CampusTraceNpm = (Get-Command npm.cmd -ErrorAction Stop).Source
Start-Process -FilePath $CampusTraceNpm `
    -ArgumentList "run", "dev" -WorkingDirectory $CampusTraceFrontendLaunch -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $CampusTraceLogRoot "frontend.stdout.log") `
    -RedirectStandardError (Join-Path $CampusTraceLogRoot "frontend.stderr.log") | Out-Null
$CampusTraceFrontendPid = Wait-CampusTraceListener -Port 5173
if (-not $CampusTraceFrontendPid) { throw "Vite startup timed out. Inspect artifacts\logs\frontend.stderr.log." }
$CampusTraceFrontendPid | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot "frontend.pid")

Write-Host "CampusTrace started:"
& (Join-Path $PSScriptRoot 'start-xun-voice.ps1')
Write-Host "  Web http://127.0.0.1:5173/"
Write-Host "  API http://127.0.0.1:8000/api/v1/health/"
Write-Host "Run scripts\stop.cmd to stop project processes safely."
