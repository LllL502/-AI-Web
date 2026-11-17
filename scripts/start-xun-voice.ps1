. "$PSScriptRoot\common.ps1"
$voicePython = Join-Path $CampusTraceRoot 'tools\qwen-tts-env\Scripts\python.exe'
$voiceModel = Join-Path $CampusTraceRoot 'data\local-voice\Qwen3-TTS-12Hz-1.7B-VoiceDesign\model.safetensors'
if (-not (Test-Path -LiteralPath $voiceModel) -or -not (Test-Path -LiteralPath $voicePython)) {
    Write-Host 'Xun voice is not installed yet.'
    exit 0
}
if (Get-CampusTraceListenerPid -Port 11436) { exit 0 }
New-Item -ItemType Directory -Force -Path $CampusTraceLogRoot | Out-Null
Start-Process -FilePath $voicePython -ArgumentList 'scripts/xun_voice_server.py' `
    -WorkingDirectory $CampusTraceRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $CampusTraceLogRoot 'voice.stdout.log') `
    -RedirectStandardError (Join-Path $CampusTraceLogRoot 'voice.stderr.log') | Out-Null
$voicePid = Wait-CampusTraceListener -Port 11436
if (-not $voicePid) { throw 'Xun voice startup failed. Inspect artifacts/logs/voice.stderr.log.' }
$voicePid | Set-Content -LiteralPath (Join-Path $CampusTraceLogRoot 'voice.pid')
