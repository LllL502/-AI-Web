$ErrorActionPreference = 'Stop'
$AiProjectRoot = Split-Path -Parent $PSScriptRoot
$AiExe = Join-Path $AiProjectRoot 'tools\ollama\ollama.exe'
$AiLogRoot = Join-Path $AiProjectRoot 'artifacts\logs'
if (-not (Test-Path -LiteralPath $AiExe)) { throw 'Project-local Ollama is not installed.' }
$env:OLLAMA_HOST = '127.0.0.1:11435'
$AiPhysicalRoot = $AiProjectRoot
$AiAncestor = Get-Item -LiteralPath $AiProjectRoot
$AiSuffix = ''
while ($AiAncestor) {
    $AiAncestor = Get-Item -LiteralPath $AiAncestor.FullName
    if ($AiAncestor.LinkType -eq 'Junction') {
        $AiPhysicalRoot = if ($AiSuffix) { Join-Path $AiAncestor.Target $AiSuffix } else { $AiAncestor.Target }
        break
    }
    $AiSuffix = if ($AiSuffix) { Join-Path $AiAncestor.Name $AiSuffix } else { $AiAncestor.Name }
    $AiAncestor = $AiAncestor.Parent
}
$env:OLLAMA_MODELS = Join-Path $AiPhysicalRoot 'data\local-models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$AiInternetSettings = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
if ($AiInternetSettings.ProxyEnable -eq 1 -and $AiInternetSettings.ProxyServer -match '^127\.0\.0\.1:\d+$') {
    $env:HTTPS_PROXY = 'http://' + $AiInternetSettings.ProxyServer
    $env:HTTP_PROXY = $env:HTTPS_PROXY
    $env:NO_PROXY = '127.0.0.1,localhost,::1'
}
foreach ($AiDirectory in @($AiLogRoot, $env:OLLAMA_MODELS)) {
    if (-not (Test-Path -LiteralPath $AiDirectory)) {
        New-Item -ItemType Directory -Path $AiDirectory | Out-Null
    }
}
try {
    $AiExisting = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2
    Write-Host "Local AI already responds: $($AiExisting.version)"
    exit 0
} catch { }
$AiProcess = Start-Process -FilePath $AiExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
    -WorkingDirectory $AiProjectRoot -RedirectStandardOutput (Join-Path $AiLogRoot 'local-ai.stdout.log') `
    -RedirectStandardError (Join-Path $AiLogRoot 'local-ai.stderr.log')
$AiProcess.Id | Set-Content -LiteralPath (Join-Path $AiLogRoot 'local-ai.pid')
for ($AiAttempt = 0; $AiAttempt -lt 40; $AiAttempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $AiVersion = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2
        Write-Host "Local AI ready on 127.0.0.1:11435: $($AiVersion.version)"
        exit 0
    } catch { }
}
throw 'Local AI startup timed out. Check artifacts/logs/local-ai.stderr.log.'
