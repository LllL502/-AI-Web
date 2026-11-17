. "$PSScriptRoot\common.ps1"

$CampusTraceCloudflared = Join-Path $CampusTraceRoot "tools\cloudflared\cloudflared.exe"
$CampusTracePublicUrlPath = Join-Path $CampusTraceLogRoot "public-test-url.txt"
$CampusTracePublicBackendPort = 8010
$CampusTracePublicFrontendPort = 4173
$CampusTracePublicDatabase = "campustrace_public_demo"
$CampusTracePublicMediaRoot = Join-Path $CampusTraceBackend "public-media"

Mount-CampusTraceRuntime
Start-CampusTraceMySql
$CampusTracePublicManage = Join-Path $CampusTraceBackendLaunch "manage.py"
New-Item -ItemType Directory -Force -Path $CampusTraceLogRoot | Out-Null
New-Item -ItemType Directory -Force -Path $CampusTracePublicMediaRoot | Out-Null

# 公网演示使用独立数据库，只装载固定合成数据。绝不复用本地 campustrace
# 数据库，避免本地账号、用户发布和上传文件被意外带到公网。
$CampusTracePublicDatabaseSql = 'CREATE DATABASE IF NOT EXISTS {0} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL PRIVILEGES ON {0}.* TO ''campustrace''@''127.0.0.1''; FLUSH PRIVILEGES;' -f $CampusTracePublicDatabase
& $CampusTraceMySql --protocol=TCP --host=127.0.0.1 --port=3307 --user=root --execute=$CampusTracePublicDatabaseSql
if ($LASTEXITCODE -ne 0) { throw "Creating the isolated public demo database failed." }

$CampusTraceSavedDatabase = [Environment]::GetEnvironmentVariable("MYSQL_DATABASE", "Process")
$env:MYSQL_DATABASE = $CampusTracePublicDatabase

try {
    # 在启动服务前先幂等执行迁移，避免新代码已构建而数据库仍是旧结构。
    & $CampusTracePython $CampusTracePublicManage migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed. Public test was not started." }
    $CampusTraceDemoCountOutput = & $CampusTracePython $CampusTracePublicManage shell -c "from apps.items.models import Item; print(Item.objects.filter(is_demo=True).count())"
    $CampusTraceDemoCount = [int](($CampusTraceDemoCountOutput | Select-Object -Last 1).Trim())
    if ($CampusTraceDemoCount -eq 0) {
        & $CampusTracePython $CampusTracePublicManage seed_demo
        if ($LASTEXITCODE -ne 0) { throw "Seeding the isolated public demo database failed." }
    }
    & $CampusTracePython $CampusTracePublicManage import_schools
    if ($LASTEXITCODE -ne 0) { throw "Importing the public school directory failed." }
} finally {
    [Environment]::SetEnvironmentVariable("MYSQL_DATABASE", $CampusTraceSavedDatabase, "Process")
}

if (-not (Test-Path -LiteralPath $CampusTraceCloudflared)) {
    throw "cloudflared is missing. Run scripts\setup-public-test.cmd first."
}
if ((Get-CampusTraceListenerPid -Port $CampusTracePublicBackendPort) -or
    (Get-CampusTraceListenerPid -Port $CampusTracePublicFrontendPort)) {
    throw "Public test ports are already in use. Run scripts\stop-public-test.cmd first."
}

$CampusTraceNpm = (Get-Command npm.cmd -ErrorAction Stop).Source
Write-Host "Checking the production frontend..."
$CampusTraceDistIndex = Join-Path $CampusTraceFrontendLaunch 'dist\index.html'
$CampusTraceBuildInputs = @()
foreach ($CampusTraceInputDirectory in @('src','public')) {
    $CampusTraceBuildInputs += Get-ChildItem -LiteralPath (Join-Path $CampusTraceFrontendLaunch $CampusTraceInputDirectory) -Recurse -File
}
$CampusTraceBuildInputs += Get-ChildItem -LiteralPath $CampusTraceFrontendLaunch -File | Where-Object { $_.Name -match '\.(json|ts|html)$' }
$CampusTraceNeedsBuild = -not (Test-Path -LiteralPath $CampusTraceDistIndex)
if (-not $CampusTraceNeedsBuild) {
    $CampusTraceBuiltAt = (Get-Item -LiteralPath $CampusTraceDistIndex).LastWriteTimeUtc
    $CampusTraceNeedsBuild = @($CampusTraceBuildInputs | Where-Object { $_.LastWriteTimeUtc -gt $CampusTraceBuiltAt }).Count -gt 0
}
if ($CampusTraceNeedsBuild) {
    & $CampusTraceNpm --prefix $CampusTraceFrontendLaunch run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
} else {
    Write-Host "Frontend is unchanged; reusing the existing production build."
}

$CampusTraceSavedEnvironment = @{}
$CampusTraceEnvironmentOverrides = @{
    DJANGO_DEBUG = "false"
    DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,.trycloudflare.com"
    DJANGO_PUBLIC_TEST = "true"
    DJANGO_SECURE_COOKIES = "true"
    DJANGO_CSRF_TRUSTED_ORIGINS = "https://*.trycloudflare.com"
    DJANGO_PUBLIC_TEST_BLOCKED_USERNAMES = "admin_demo,staff_east,staff_west,student_01,student_02,student_03,student_04,student_05,student_06,student_07,student_08"
    DJANGO_MEDIA_ROOT = $CampusTracePublicMediaRoot
    MYSQL_DATABASE = $CampusTracePublicDatabase
    CAMPUS_TRACE_PUBLIC_BACKEND = "127.0.0.1:$CampusTracePublicBackendPort"
}
foreach ($CampusTraceEnvironmentName in $CampusTraceEnvironmentOverrides.Keys) {
    $CampusTraceSavedEnvironment[$CampusTraceEnvironmentName] = [Environment]::GetEnvironmentVariable($CampusTraceEnvironmentName, "Process")
    [Environment]::SetEnvironmentVariable(
        $CampusTraceEnvironmentName,
        $CampusTraceEnvironmentOverrides[$CampusTraceEnvironmentName],
        "Process"
    )
}

try {
    Start-Process -FilePath $CampusTracePython `
        -ArgumentList "-m", "config.serve" -WorkingDirectory $CampusTraceBackendLaunch -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $CampusTraceLogRoot "public-backend.stdout.log") `
        -RedirectStandardError (Join-Path $CampusTraceLogRoot "public-backend.stderr.log") | Out-Null
    $CampusTracePublicBackendPid = Wait-CampusTraceListener -Port $CampusTracePublicBackendPort
    if (-not $CampusTracePublicBackendPid) { throw "Public backend startup timed out." }
    $CampusTracePublicBackendPid | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot "public-backend.pid")
} finally {
    foreach ($CampusTraceEnvironmentName in $CampusTraceEnvironmentOverrides.Keys) {
        [Environment]::SetEnvironmentVariable(
            $CampusTraceEnvironmentName,
            $CampusTraceSavedEnvironment[$CampusTraceEnvironmentName],
            "Process"
        )
    }
}

$CampusTraceSavedApiTarget = [Environment]::GetEnvironmentVariable("CAMPUS_TRACE_API_TARGET", "Process")
$env:CAMPUS_TRACE_API_TARGET = "http://127.0.0.1:$CampusTracePublicBackendPort"
try {
    Start-Process -FilePath $CampusTraceNpm `
        -ArgumentList "run", "preview" -WorkingDirectory $CampusTraceFrontendLaunch -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $CampusTraceLogRoot "public-frontend.stdout.log") `
        -RedirectStandardError (Join-Path $CampusTraceLogRoot "public-frontend.stderr.log") | Out-Null
    $CampusTracePublicFrontendPid = Wait-CampusTraceListener -Port $CampusTracePublicFrontendPort
    if (-not $CampusTracePublicFrontendPid) { throw "Public frontend startup timed out." }
    $CampusTracePublicFrontendPid | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot "public-frontend.pid")
} finally {
    [Environment]::SetEnvironmentVariable("CAMPUS_TRACE_API_TARGET", $CampusTraceSavedApiTarget, "Process")
}

$CampusTraceTunnelStdout = Join-Path $CampusTraceLogRoot "public-tunnel.stdout.log"
$CampusTraceTunnelStderr = Join-Path $CampusTraceLogRoot "public-tunnel.stderr.log"
# A listening port is not enough: verify the website and database-backed API.
try {
    $CampusTraceLocalPage = Invoke-WebRequest -Uri "http://127.0.0.1:$CampusTracePublicFrontendPort/home" -UseBasicParsing -TimeoutSec 15
    $CampusTraceLocalHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$CampusTracePublicFrontendPort/api/v1/health/" -TimeoutSec 15
    if ($CampusTraceLocalPage.StatusCode -ne 200 -or $CampusTraceLocalHealth.data.status -ne 'ok') { throw 'Local health check failed.' }
} catch {
    & "$PSScriptRoot\stop-public-test.ps1"
    throw "Local website/API health check failed. Inspect public-backend and public-frontend logs."
}
Write-Host "Local website and API are ready. Connecting the public tunnel using HTTP/2..."
$CampusTraceTunnelProcess = Start-Process -FilePath $CampusTraceCloudflared `
    -ArgumentList "tunnel", "--no-autoupdate", "--protocol", "http2", "--edge-ip-version", "4", "--url", "http://127.0.0.1:$CampusTracePublicFrontendPort" `
    -WorkingDirectory (Split-Path -Parent $CampusTraceCloudflared) -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $CampusTraceTunnelStdout -RedirectStandardError $CampusTraceTunnelStderr
$CampusTraceTunnelProcess.Id | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot "public-tunnel.pid")

$CampusTracePublicUrl = $null
for ($CampusTraceAttempt = 0; $CampusTraceAttempt -lt 60; $CampusTraceAttempt++) {
    Start-Sleep -Milliseconds 500
    $CampusTraceTunnelLog = ""
    if (Test-Path -LiteralPath $CampusTraceTunnelStderr) {
        $CampusTraceTunnelLog += Get-Content -LiteralPath $CampusTraceTunnelStderr -Raw -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $CampusTraceTunnelStdout) {
        $CampusTraceTunnelLog += Get-Content -LiteralPath $CampusTraceTunnelStdout -Raw -ErrorAction SilentlyContinue
    }
    $CampusTraceUrlMatch = [regex]::Match($CampusTraceTunnelLog, "https://[a-z0-9-]+\.trycloudflare\.com")
    if ($CampusTraceUrlMatch.Success -and $CampusTraceTunnelLog -match 'Registered tunnel connection') {
        $CampusTracePublicUrl = $CampusTraceUrlMatch.Value
        break
    }
    if ($CampusTraceTunnelProcess.HasExited) { break }
}

if (-not $CampusTracePublicUrl) {
    try { & "$PSScriptRoot\stop-public-test.ps1" } catch { Write-Warning "Cleanup failed: $($_.Exception.Message)" }
    throw "Cloudflare tunnel did not establish a connection. Check outbound TCP 7844/network and artifacts\logs\public-tunnel.stderr.log. A generated URL alone is not sufficient."
}
# Verify the public website and API before publishing a shareable URL.
$CampusTracePublicVerified = $false
Write-Host "Tunnel connected. Verifying the public website and API..."
for ($CampusTraceVerifyAttempt=0; $CampusTraceVerifyAttempt -lt 2; $CampusTraceVerifyAttempt++) {
    try {
        $CampusTracePublicPage = Invoke-WebRequest -Uri "$CampusTracePublicUrl/home" -UseBasicParsing -TimeoutSec 5
        $CampusTracePublicHealth = Invoke-RestMethod -Uri "$CampusTracePublicUrl/api/v1/health/" -TimeoutSec 5
        if ($CampusTracePublicPage.StatusCode -eq 200 -and $CampusTracePublicHealth.data.status -eq 'ok') {
            $CampusTracePublicVerified = $true
            break
        }
    } catch { }
    Write-Host "Public verification pending ($($CampusTraceVerifyAttempt+1)/2)..."
    Start-Sleep -Milliseconds 500
}
if (-not $CampusTracePublicVerified) {
    # Some local networks cannot visit their own Quick Tunnel URL even when the
    # tunnel is registered. Keep the connected tunnel alive and let the user
    # verify it from another browser/device instead of stopping all services.
    Write-Warning "This computer could not verify the public URL. The tunnel remains online; test the link in an external browser or mobile network."
}
$CampusTracePublicUrl | Set-Content -LiteralPath $CampusTracePublicUrlPath -Encoding utf8
Write-Host ""
Write-Host "CampusTrace public test is online:"
Write-Host "  $CampusTracePublicUrl"
if (-not $CampusTracePublicVerified) {
    Write-Host "  Status: tunnel connected; external access was not verified from this computer."
}
Write-Host ""
Write-Host "This random URL remains valid only while this process and computer stay online."
Write-Host "Run scripts\stop-public-test.cmd in another terminal to stop it."

Wait-Process -Id $CampusTraceTunnelProcess.Id
& "$PSScriptRoot\stop-public-test.ps1"
