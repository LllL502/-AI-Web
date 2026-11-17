. "$PSScriptRoot\common.ps1"

$CampusTraceServiceSpecs = @(
    @{ Name = "voice"; Port = 11436; Pattern = "xun_voice_server\.py" },
    @{ Name = "frontend"; Port = 5173; Pattern = "vite.*--port 5173" },
    @{ Name = "backend"; Port = 8000; Pattern = "manage\.py runserver 127\.0\.0\.1:8000" }
)

foreach ($CampusTraceSpec in $CampusTraceServiceSpecs) {
    $CampusTraceService = $CampusTraceSpec.Name
    $CampusTracePidPath = Join-Path $CampusTraceLogRoot "$CampusTraceService.pid"
    $CampusTraceCandidatePids = @()
    if (Test-Path -LiteralPath $CampusTracePidPath) {
        $CampusTraceCandidatePids += [int](Get-Content -LiteralPath $CampusTracePidPath -Raw)
        Remove-Item -LiteralPath $CampusTracePidPath -Force
    }
    $CampusTracePortPid = Get-CampusTraceListenerPid -Port $CampusTraceSpec.Port
    if ($CampusTracePortPid) { $CampusTraceCandidatePids += $CampusTracePortPid }
    foreach ($CampusTraceServicePid in ($CampusTraceCandidatePids | Select-Object -Unique)) {
        $CampusTraceProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $CampusTraceServicePid" -ErrorAction SilentlyContinue
        if ($CampusTraceProcess -and $CampusTraceProcess.CommandLine -match $CampusTraceSpec.Pattern) {
            Stop-Process -Id $CampusTraceServicePid -ErrorAction SilentlyContinue
        }
    }
}

$CampusTracePublicStillRunning = (Get-CampusTraceListenerPid -Port 8010) -or (Get-CampusTraceListenerPid -Port 4173)
if ((Test-CampusTraceMySql) -and -not $CampusTracePublicStillRunning) {
    $CampusTraceMySqlStopPid = Get-CampusTraceListenerPid -Port 3307
    $CampusTraceStopErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $CampusTraceMySqlAdmin --protocol=TCP --host=127.0.0.1 --port=3307 --user=campustrace --password=campustrace-local-only shutdown 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # The project bootstrap account has no global SHUTDOWN privilege.
        & $CampusTraceMySqlAdmin --protocol=TCP --host=127.0.0.1 --port=3307 --user=root shutdown 2>$null | Out-Null
    }
    $ErrorActionPreference = $CampusTraceStopErrorPreference
    if ($CampusTraceMySqlStopPid) {
        Wait-Process -Id $CampusTraceMySqlStopPid -Timeout 30 -ErrorAction SilentlyContinue
        if (Get-Process -Id $CampusTraceMySqlStopPid -ErrorAction SilentlyContinue) {
            throw 'MySQL has not fully exited; runtime path preserved for data safety.'
        }
    }
}
if (-not $CampusTracePublicStillRunning) {
    if (Test-Path -LiteralPath (Join-Path $CampusTraceRoot 'tools\ollama\ollama.exe')) {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop-local-ai.ps1')
    }
    Dismount-CampusTraceRuntime
    Write-Host "CampusTrace local processes stopped. Database files remain in data\mysql\data."
} else {
    Write-Host "CampusTrace local processes stopped. MySQL and runtime junction remain active for the public test."
}
