$ErrorActionPreference = 'Stop'
$AiProjectRoot = Split-Path -Parent $PSScriptRoot
$AiArchive = Join-Path $AiProjectRoot 'tools\ollama-windows-amd64-verified.zip'
$AiExpectedHash = '50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e'
if (-not (Test-Path -LiteralPath $AiArchive)) { throw 'Run scripts/download-local-ai.py first.' }
if ((Get-FileHash -LiteralPath $AiArchive -Algorithm SHA256).Hash.ToLower() -ne $AiExpectedHash) {
    throw 'Official runtime SHA-256 mismatch. Refusing to execute.'
}
Expand-Archive -LiteralPath $AiArchive -DestinationPath (Join-Path $AiProjectRoot 'tools\ollama') -Force
& (Join-Path $AiProjectRoot 'tools\ollama\ollama.exe') --version
