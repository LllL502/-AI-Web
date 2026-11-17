$ErrorActionPreference = 'Stop'
$AiProjectRoot = Split-Path -Parent $PSScriptRoot
$AiExe = Join-Path $AiProjectRoot 'tools\ollama\ollama.exe'
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $AiProjectRoot 'data\local-models'
$env:OLLAMA_NO_CLOUD = '1'
foreach ($AiModel in @('qwen3-vl:4b-instruct', 'qwen3-embedding:0.6b')) {
    & $AiExe pull $AiModel
    if ($LASTEXITCODE -ne 0) { throw "Model download failed: $AiModel. Rerun to resume." }
}
& $AiExe list
