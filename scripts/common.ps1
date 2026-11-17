$ErrorActionPreference = "Stop"

$CampusTraceScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CampusTraceRoot = Split-Path -Parent $CampusTraceScriptRoot
$CampusTraceBackend = Join-Path $CampusTraceRoot "backend"
$CampusTraceFrontend = Join-Path $CampusTraceRoot "frontend"
$CampusTraceMySqlHome = Join-Path $CampusTraceRoot "tools\mysql-8.4.11-winx64"
$CampusTraceMySqlData = Join-Path $CampusTraceRoot "data\mysql\data"
$CampusTraceLogRoot = Join-Path $CampusTraceRoot "artifacts\logs"
$CampusTracePython = Join-Path $CampusTraceBackend ".venv\Scripts\python.exe"
$CampusTraceMySql = Join-Path $CampusTraceMySqlHome "bin\mysql.exe"
$CampusTraceMySqlAdmin = Join-Path $CampusTraceMySqlHome "bin\mysqladmin.exe"
$CampusTraceMySqlServer = Join-Path $CampusTraceMySqlHome "bin\mysqld.exe"
$CampusTraceLaunchRoot = Join-Path ([System.IO.Path]::GetTempPath()) "CampusTrace-AIC8-Runtime"
$CampusTraceMySqlLaunchHome = Join-Path $CampusTraceLaunchRoot "tools\mysql-8.4.11-winx64"
$CampusTraceMySqlLaunchServer = "$CampusTraceMySqlLaunchHome\bin\mysqld.exe"
$CampusTraceBackendLaunch = Join-Path $CampusTraceLaunchRoot "backend"
$CampusTraceFrontendLaunch = Join-Path $CampusTraceLaunchRoot "frontend"

function Mount-CampusTraceRuntime {
    $CampusTraceManagePath = Join-Path $CampusTraceLaunchRoot "backend\manage.py"
    $CampusTracePackagePath = Join-Path $CampusTraceLaunchRoot "frontend\package.json"
    if (Test-Path -LiteralPath $CampusTraceLaunchRoot) {
        $CampusTraceRuntimeItem = Get-Item -LiteralPath $CampusTraceLaunchRoot -Force
        if (($CampusTraceRuntimeItem.LinkType -eq "Junction") -and
            (Test-Path -LiteralPath $CampusTraceManagePath) -and
            (Test-Path -LiteralPath $CampusTracePackagePath)) { return }
        throw "$CampusTraceLaunchRoot already exists and is not the CampusTrace runtime junction."
    }
    New-Item -ItemType Junction -Path $CampusTraceLaunchRoot -Target $CampusTraceRoot | Out-Null
}

function Dismount-CampusTraceRuntime {
    if (-not (Test-Path -LiteralPath $CampusTraceLaunchRoot)) { return }
    $CampusTraceRuntimeItem = Get-Item -LiteralPath $CampusTraceLaunchRoot -Force
    if (($CampusTraceRuntimeItem.LinkType -eq "Junction") -and
        (Test-Path -LiteralPath (Join-Path $CampusTraceLaunchRoot "backend\manage.py")) -and
        (Test-Path -LiteralPath (Join-Path $CampusTraceLaunchRoot "frontend\package.json"))) {
        # Verify the junction target before non-recursive deletion.
        # Delete only the reparse point, never traverse project files.
        $CampusTraceExpectedTarget = [System.IO.Path]::GetFullPath($CampusTraceRoot).TrimEnd('\')
        $CampusTraceActualTargets = @($CampusTraceRuntimeItem.Target)
        if ($CampusTraceActualTargets.Count -ne 1 -or
            [System.IO.Path]::GetFullPath($CampusTraceActualTargets[0]).TrimEnd('\') -ne $CampusTraceExpectedTarget) {
            throw "Runtime junction target does not match this project; cleanup refused."
        }
        [System.IO.Directory]::Delete($CampusTraceLaunchRoot, $false)
    }
}

function Test-CampusTraceMySql {
    if (-not (Test-Path -LiteralPath $CampusTraceMySqlAdmin)) { return $false }
    $CampusTraceErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $CampusTraceMySqlAdmin --protocol=TCP --host=127.0.0.1 --port=3307 --connect-timeout=1 --user=campustrace --password=campustrace-local-only ping --silent 2>$null | Out-Null
    $CampusTraceAppPing = $LASTEXITCODE
    $ErrorActionPreference = $CampusTraceErrorPreference
    if ($CampusTraceAppPing -eq 0) { return $true }
    # The scoped account does not exist during first boot; local root performs bootstrap only.
    $ErrorActionPreference = "SilentlyContinue"
    & $CampusTraceMySqlAdmin --protocol=TCP --host=127.0.0.1 --port=3307 --connect-timeout=1 --user=root ping --silent 2>$null | Out-Null
    $CampusTraceRootPing = $LASTEXITCODE
    $ErrorActionPreference = $CampusTraceErrorPreference
    return $CampusTraceRootPing -eq 0
}

function Get-CampusTraceListenerPid([int]$Port) {
    $CampusTraceListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::1", "::") } |
        Select-Object -First 1
    if ($CampusTraceListener) { return [int]$CampusTraceListener.OwningProcess }
    return $null
}

function Wait-CampusTraceListener([int]$Port, [int]$Attempts = 40) {
    for ($CampusTraceAttempt = 0; $CampusTraceAttempt -lt $Attempts; $CampusTraceAttempt++) {
        $CampusTraceListenerPid = Get-CampusTraceListenerPid -Port $Port
        if ($CampusTraceListenerPid) { return $CampusTraceListenerPid }
        Start-Sleep -Milliseconds 250
    }
    return $null
}

function Start-CampusTraceMySql {
    if (Test-CampusTraceMySql) { return }
    if (-not (Test-Path -LiteralPath $CampusTraceMySqlServer)) {
        throw "Project-local MySQL was not found. Run scripts\setup.cmd first."
    }
    Mount-CampusTraceRuntime
    New-Item -ItemType Directory -Force -Path $CampusTraceLogRoot | Out-Null
    $CampusTraceMySqlArgs = @(
        "--no-defaults",
        "--basedir=$CampusTraceMySqlLaunchHome",
        "--datadir=$(Join-Path $CampusTraceLaunchRoot 'data\mysql\data')",
        "--port=3307",
        "--bind-address=127.0.0.1",
        "--mysqlx=0",
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_0900_ai_ci",
        "--pid-file=$(Join-Path $CampusTraceLaunchRoot 'artifacts\logs\mysql.pid')"
    )
    Start-Process -FilePath $CampusTraceMySqlLaunchServer -ArgumentList $CampusTraceMySqlArgs -WorkingDirectory $CampusTraceMySqlLaunchHome -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $CampusTraceLogRoot "mysql.stdout.log") `
        -RedirectStandardError (Join-Path $CampusTraceLogRoot "mysql.stderr.log") | Out-Null
    for ($CampusTraceAttempt = 0; $CampusTraceAttempt -lt 30; $CampusTraceAttempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-CampusTraceMySql) { return }
    }
    throw "MySQL startup timed out. Inspect artifacts\logs\mysql.stderr.log."
}
