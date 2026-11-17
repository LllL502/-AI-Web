. "$PSScriptRoot\common.ps1"

Write-Host "[1/7] Check project directories"
New-Item -ItemType Directory -Force -Path $CampusTraceMySqlData, $CampusTraceLogRoot | Out-Null
Mount-CampusTraceRuntime

Write-Host "[2/7] Extract project-local MySQL 8.4.11"
$CampusTraceMySqlArchive = Join-Path $CampusTraceRoot "tools\mysql-8.4.11-winx64.zip"
if (-not (Test-Path -LiteralPath $CampusTraceMySqlHome)) {
    if (-not (Test-Path -LiteralPath $CampusTraceMySqlArchive)) {
        throw "Missing $CampusTraceMySqlArchive. Download the official MySQL 8.4.11 Windows ZIP first."
    }
    Expand-Archive -LiteralPath $CampusTraceMySqlArchive -DestinationPath (Join-Path $CampusTraceRoot "tools")
}

Write-Host "[3/7] Initialize MySQL data directory"
if (-not (Test-Path -LiteralPath (Join-Path $CampusTraceMySqlData "mysql"))) {
    Push-Location $CampusTraceMySqlLaunchHome
    & ".\bin\mysqld.exe" --no-defaults --initialize-insecure "--basedir=$CampusTraceMySqlLaunchHome" "--datadir=$(Join-Path $CampusTraceLaunchRoot 'data\mysql\data')"
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "MySQL data initialization failed" }
}

Write-Host "[4/7] Start MySQL on 127.0.0.1:3307 only"
Start-CampusTraceMySql

Write-Host "[5/7] Create database and scoped application account"
$CampusTraceBootstrapSql = @"
CREATE DATABASE IF NOT EXISTS campustrace CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'campustrace'@'127.0.0.1' IDENTIFIED BY 'campustrace-local-only';
ALTER USER 'campustrace'@'127.0.0.1' IDENTIFIED BY 'campustrace-local-only';
GRANT ALL PRIVILEGES ON campustrace.* TO 'campustrace'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_campustrace.* TO 'campustrace'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
& $CampusTraceMySql --protocol=TCP --host=127.0.0.1 --port=3307 --user=root --execute=$CampusTraceBootstrapSql
if ($LASTEXITCODE -ne 0) { throw "Creating the CampusTrace database failed" }

Write-Host "[6/7] Install Python and frontend dependencies"
if (-not (Test-Path -LiteralPath $CampusTracePython)) {
    python -m venv (Join-Path $CampusTraceBackend ".venv")
}
& $CampusTracePython -m pip install --disable-pip-version-check -r (Join-Path $CampusTraceBackend "requirements.lock")
Push-Location $CampusTraceFrontendLaunch
npm install --no-audit --no-fund
Pop-Location

Write-Host "[7/7] Write local config, migrate, and seed deterministic demo data"
$CampusTraceEnvPath = Join-Path $CampusTraceBackend ".env"
if (-not (Test-Path -LiteralPath $CampusTraceEnvPath)) {
    $CampusTraceSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object {[char]$_})
    $CampusTraceEnvContent = @"
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=$CampusTraceSecret
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
MYSQL_DATABASE=campustrace
MYSQL_USER=campustrace
MYSQL_PASSWORD=campustrace-local-only
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
DEMO_BASE_DATE=2026-08-20T08:00:00+08:00
"@
    [System.IO.File]::WriteAllText($CampusTraceEnvPath, $CampusTraceEnvContent, (New-Object System.Text.UTF8Encoding($false)))
}
Push-Location $CampusTraceBackendLaunch
& $CampusTracePython manage.py migrate
& $CampusTracePython manage.py seed_demo
Pop-Location

Write-Host "Setup complete. Run scripts\start.cmd and open http://127.0.0.1:5173/"
