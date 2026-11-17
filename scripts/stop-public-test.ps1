. "$PSScriptRoot\common.ps1"

$CampusTracePublicSpecs = @(
    @{ Name = "public-frontend"; Port = 4173; Pattern = "vite.*preview" },
    @{ Name = "public-backend"; Port = 8010; Pattern = "config\.serve" }
)

foreach ($CampusTraceSpec in $CampusTracePublicSpecs) {
    $CampusTraceCandidatePids = @()
    $CampusTracePidPath = Join-Path $CampusTraceLogRoot "$($CampusTraceSpec.Name).pid"
    if (Test-Path -LiteralPath $CampusTracePidPath) {
        $CampusTraceCandidatePids += [int](Get-Content -LiteralPath $CampusTracePidPath -Raw)
        Remove-Item -LiteralPath $CampusTracePidPath -Force
    }
    $CampusTraceListenerPid = Get-CampusTraceListenerPid -Port $CampusTraceSpec.Port
    if ($CampusTraceListenerPid) { $CampusTraceCandidatePids += $CampusTraceListenerPid }
    foreach ($CampusTraceServicePid in ($CampusTraceCandidatePids | Select-Object -Unique)) {
        $CampusTraceProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $CampusTraceServicePid" -ErrorAction SilentlyContinue
        if ($CampusTraceProcess -and $CampusTraceProcess.CommandLine -match $CampusTraceSpec.Pattern) {
            Stop-Process -Id $CampusTraceServicePid -ErrorAction SilentlyContinue
        }
    }
}

$CampusTraceTunnelPidPath = Join-Path $CampusTraceLogRoot "public-tunnel.pid"
if (Test-Path -LiteralPath $CampusTraceTunnelPidPath) {
    $CampusTraceTunnelPid = [int](Get-Content -LiteralPath $CampusTraceTunnelPidPath -Raw)
    Remove-Item -LiteralPath $CampusTraceTunnelPidPath -Force
    $CampusTraceTunnelProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $CampusTraceTunnelPid" -ErrorAction SilentlyContinue
    if ($CampusTraceTunnelProcess -and $CampusTraceTunnelProcess.CommandLine -match "cloudflared.*tunnel.*127\.0\.0\.1:4173") {
        Stop-Process -Id $CampusTraceTunnelPid -ErrorAction SilentlyContinue
    }
}

$CampusTracePublicUrlPath = Join-Path $CampusTraceLogRoot "public-test-url.txt"
if (Test-Path -LiteralPath $CampusTracePublicUrlPath) {
    Remove-Item -LiteralPath $CampusTracePublicUrlPath -Force
}
$CampusTraceLocalStillRunning = (Get-CampusTraceListenerPid -Port 8000) -or (Get-CampusTraceListenerPid -Port 5173)
if (-not $CampusTraceLocalStillRunning) {
    if (Test-CampusTraceMySql) {
        $CampusTraceStopErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & $CampusTraceMySqlAdmin --protocol=TCP --host=127.0.0.1 --port=3307 --user=campustrace --password=campustrace-local-only shutdown 2>$null | Out-Null
        $ErrorActionPreference = $CampusTraceStopErrorPreference
    }
    Dismount-CampusTraceRuntime
    Write-Host "CampusTrace public test and its local database process stopped. Database files were preserved."
} else {
    Write-Host "CampusTrace public test stopped. Local services and database remain running."
}
