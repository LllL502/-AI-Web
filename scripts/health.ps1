. "$PSScriptRoot\common.ps1"

$CampusTraceChecks = @()
$CampusTraceChecks += [pscustomobject]@{ Name = "MySQL 8.4"; Ok = (Test-CampusTraceMySql); Target = "127.0.0.1:3307" }
try {
    $CampusTraceApi = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health/?dependencies=1" -TimeoutSec 12
    foreach ($taskModel in @(@("extraction", "Xun dialogue"), @("embedding", "Semantic retrieval"), @("vision", "Image model"), @("voice", "Xun voice"))) {
        $taskStatus=$CampusTraceApi.data.assistant.models.($taskModel[0]); $CampusTraceChecks += [pscustomobject]@{Name=$taskModel[1]; Ok=($taskStatus.ready -eq $true); Target=$taskStatus.state}
    }
    $CampusTraceChecks += [pscustomobject]@{ Name = "Django API"; Ok = ($CampusTraceApi.data.status -eq "ok"); Target = "127.0.0.1:8000" }
} catch {
    $CampusTraceChecks += [pscustomobject]@{ Name = "Django API"; Ok = $false; Target = "127.0.0.1:8000" }
}
try {
    $CampusTraceWeb = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -TimeoutSec 5 -UseBasicParsing
    $CampusTraceChecks += [pscustomobject]@{ Name = "Vue Web"; Ok = ($CampusTraceWeb.StatusCode -eq 200); Target = "127.0.0.1:5173" }
} catch {
    $CampusTraceChecks += [pscustomobject]@{ Name = "Vue Web"; Ok = $false; Target = "127.0.0.1:5173" }
}
$CampusTraceChecks | Format-Table -AutoSize
if ($CampusTraceChecks.Ok -contains $false) { exit 1 }
