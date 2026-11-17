. "$PSScriptRoot\common.ps1"

$CampusTracePublicUrlPath = Join-Path $CampusTraceLogRoot "public-test-url.txt"
$CampusTraceEvidencePath = Join-Path $CampusTraceRoot "artifacts\public-test-evidence.json"
if (-not (Test-Path -LiteralPath $CampusTracePublicUrlPath)) {
    throw "Public URL is missing. Run scripts\start-public-test.cmd first."
}

$CampusTracePublicUrl = (Get-Content -LiteralPath $CampusTracePublicUrlPath -Raw).Trim()
$CampusTracePublicDatabase = "campustrace_public_demo"
$CampusTraceSmokeUsername = "public_smoke_$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$CampusTraceSmokePassword = "$([guid]::NewGuid().ToString('N'))Aa!9"
$CampusTraceSmokeCreated = $false
$CampusTraceChecks = [ordered]@{
    health = $false
    home = $false
    register_as_user = $false
    registration_session = $false
    login_session = $false
    secure_csrf_cookie = $false
    secure_session_cookie = $false
    fixed_admin_blocked = $false
    fixed_staff_blocked = $false
    fixed_student_blocked = $false
    temporary_account_removed = $false
}
$CampusTraceFailure = $null

function New-CampusTraceCsrfSession {
    $CampusTraceSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/csrf/") -WebSession $CampusTraceSession -TimeoutSec 20 | Out-Null
    return $CampusTraceSession
}

function Test-CampusTraceFixedLoginBlocked([string]$Username) {
    $CampusTraceSession = New-CampusTraceCsrfSession
    $CampusTraceCookie = $CampusTraceSession.Cookies.GetCookies($CampusTracePublicUrl)["csrftoken"]
    $CampusTraceHeaders = @{
        "X-CSRFToken" = $CampusTraceCookie.Value
        "Origin" = $CampusTracePublicUrl
        "Referer" = ($CampusTracePublicUrl + "/login")
    }
    $CampusTraceBody = @{ username = $Username; password = "CampusTrace!2026" } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/login/") -Method Post `
            -ContentType "application/json" -Body $CampusTraceBody -Headers $CampusTraceHeaders `
            -WebSession $CampusTraceSession -TimeoutSec 20 | Out-Null
        return $false
    } catch {
        return $_.Exception.Response.StatusCode.value__ -eq 400
    }
}

try {
    $CampusTraceHealth = Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/health/") -TimeoutSec 20
    $CampusTraceChecks.health = $CampusTraceHealth.data.status -eq "ok"
    $CampusTraceHomeResponse = Invoke-WebRequest -Uri ($CampusTracePublicUrl + "/") -UseBasicParsing -TimeoutSec 20
    $CampusTraceChecks.home = $CampusTraceHomeResponse.StatusCode -eq 200

    $CampusTraceRegisterSession = New-CampusTraceCsrfSession
    $CampusTraceCsrfCookie = $CampusTraceRegisterSession.Cookies.GetCookies($CampusTracePublicUrl)["csrftoken"]
    $CampusTraceRegisterHeaders = @{
        "X-CSRFToken" = $CampusTraceCsrfCookie.Value
        "Origin" = $CampusTracePublicUrl
        "Referer" = ($CampusTracePublicUrl + "/register")
    }
    $CampusTraceRegisterBody = @{
        username = $CampusTraceSmokeUsername
        display_name = "公网冒烟测试"
        email = "$CampusTraceSmokeUsername@example.test"
        password = $CampusTraceSmokePassword
    } | ConvertTo-Json
    $CampusTraceRegisterResponse = Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/register/") `
        -Method Post -ContentType "application/json" -Body $CampusTraceRegisterBody `
        -Headers $CampusTraceRegisterHeaders -WebSession $CampusTraceRegisterSession -TimeoutSec 20
    $CampusTraceSmokeCreated = $true
    $CampusTraceChecks.register_as_user = $CampusTraceRegisterResponse.data.role -eq "USER"
    $CampusTraceMeAfterRegister = Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/me/") `
        -WebSession $CampusTraceRegisterSession -TimeoutSec 20
    $CampusTraceChecks.registration_session = $CampusTraceMeAfterRegister.data.username -eq $CampusTraceSmokeUsername
    $CampusTraceSessionCookie = $CampusTraceRegisterSession.Cookies.GetCookies($CampusTracePublicUrl)["sessionid"]
    $CampusTraceChecks.secure_csrf_cookie = [bool]$CampusTraceCsrfCookie.Secure
    $CampusTraceChecks.secure_session_cookie = [bool]$CampusTraceSessionCookie.Secure

    $CampusTraceLoginSession = New-CampusTraceCsrfSession
    $CampusTraceLoginCsrf = $CampusTraceLoginSession.Cookies.GetCookies($CampusTracePublicUrl)["csrftoken"]
    $CampusTraceLoginHeaders = @{
        "X-CSRFToken" = $CampusTraceLoginCsrf.Value
        "Origin" = $CampusTracePublicUrl
        "Referer" = ($CampusTracePublicUrl + "/login")
    }
    $CampusTraceLoginBody = @{ username = $CampusTraceSmokeUsername; password = $CampusTraceSmokePassword } | ConvertTo-Json
    Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/login/") -Method Post `
        -ContentType "application/json" -Body $CampusTraceLoginBody -Headers $CampusTraceLoginHeaders `
        -WebSession $CampusTraceLoginSession -TimeoutSec 20 | Out-Null
    $CampusTraceMeAfterLogin = Invoke-RestMethod -Uri ($CampusTracePublicUrl + "/api/v1/auth/me/") `
        -WebSession $CampusTraceLoginSession -TimeoutSec 20
    $CampusTraceChecks.login_session = $CampusTraceMeAfterLogin.data.username -eq $CampusTraceSmokeUsername

    $CampusTraceChecks.fixed_admin_blocked = Test-CampusTraceFixedLoginBlocked -Username "admin_demo"
    $CampusTraceChecks.fixed_staff_blocked = Test-CampusTraceFixedLoginBlocked -Username "staff_west"
    $CampusTraceChecks.fixed_student_blocked = Test-CampusTraceFixedLoginBlocked -Username "student_08"
} catch {
    $CampusTraceFailure = $_.Exception.GetType().Name
} finally {
    if ($CampusTraceSmokeCreated) {
        $CampusTraceSavedDatabase = [Environment]::GetEnvironmentVariable("MYSQL_DATABASE", "Process")
        $env:MYSQL_DATABASE = $CampusTracePublicDatabase
        Push-Location $CampusTraceBackend
        try {
            & $CampusTracePython manage.py shell -c "from apps.accounts.models import User; User.objects.filter(username='$CampusTraceSmokeUsername').delete()" | Out-Null
            $CampusTraceRemaining = & $CampusTracePython manage.py shell -c "from apps.accounts.models import User; print(User.objects.filter(username='$CampusTraceSmokeUsername').count())"
        } finally {
            Pop-Location
            [Environment]::SetEnvironmentVariable("MYSQL_DATABASE", $CampusTraceSavedDatabase, "Process")
        }
        $CampusTraceChecks.temporary_account_removed = (($CampusTraceRemaining | Select-Object -Last 1).Trim() -eq "0")
    }
}

$CampusTracePassed = ($CampusTraceChecks.Values -notcontains $false) -and -not $CampusTraceFailure
$CampusTraceEvidence = [ordered]@{
    schema_version = 1
    generated_at = [DateTimeOffset]::Now.ToString("o")
    environment = "cloudflare_quick_tunnel"
    public_url = $CampusTracePublicUrl
    status = $(if ($CampusTracePassed) { "PASS" } else { "FAIL" })
    checks = $CampusTraceChecks
    failure_type = $CampusTraceFailure
    scope_note = "公网进程使用独立合成数据数据库与独立媒体目录；临时 USER 已清理；证据不包含密码、Cookie 或 CSRF token。Quick Tunnel 仅用于测试。"
}
$CampusTraceEvidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $CampusTraceEvidencePath -Encoding utf8
$CampusTraceEvidence | ConvertTo-Json -Depth 5
if (-not $CampusTracePassed) { exit 1 }
