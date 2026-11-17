$ErrorActionPreference = 'Stop'
$AiProjectRoot = Split-Path -Parent $PSScriptRoot
$AiPidFile = Join-Path $AiProjectRoot 'artifacts\logs\local-ai.pid'
if (Test-Path -LiteralPath $AiPidFile) {
    $AiProcessId = [int](Get-Content -LiteralPath $AiPidFile -Raw)
    $AiProcess = Get-Process -Id $AiProcessId -ErrorAction SilentlyContinue
    $AiExpectedPath = [System.IO.Path]::GetFullPath((Join-Path $AiProjectRoot 'tools\ollama\ollama.exe'))
    if ($AiProcess -and [System.IO.Path]::GetFullPath($AiProcess.Path) -eq $AiExpectedPath) {
        $env:OLLAMA_HOST = '127.0.0.1:11435'
        foreach ($AiModel in @('qwen3-vl:4b-instruct', 'qwen3-embedding:0.6b')) {
            try { & $AiExpectedPath stop $AiModel 2>$null | Out-Null } catch { }
        }
        Stop-Process -Id $AiProcessId
    }
    Remove-Item -LiteralPath $AiPidFile
}
Write-Host 'Project local AI stopped; downloaded models preserved.'
