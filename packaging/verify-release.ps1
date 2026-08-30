[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ReleaseDir,
    [switch]$SkipLaunch,
    [int]$Port = 18080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ReleaseRoot = (Resolve-Path -LiteralPath $ReleaseDir).Path
$Required = @(
    "ADS会议智能体.exe",
    "_internal\frontend\dist\index.html",
    "_internal\runtime\ffmpeg\bin\ffmpeg.exe",
    "_internal\runtime\ffmpeg\bin\ffprobe.exe",
    "_internal\backend\data\models\faster-whisper-small\model.bin",
    "_internal\backend\data\models\speaker-diarization\segmentation\model.onnx",
    "_internal\backend\data\models\speaker-diarization\wespeaker_zh_cnceleb_resnet34.onnx",
    "_internal\README.md",
    "_internal\THIRD_PARTY_NOTICES.md",
    "_internal\docs\ADS会议智能体使用教程.md"
)
foreach ($Relative in $Required) {
    $Target = Join-Path $ReleaseRoot $Relative
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "发行包缺少：$Relative" }
}
$SherpaRuntime = Get-ChildItem -LiteralPath (Join-Path $ReleaseRoot "_internal") -Recurse -File -Filter "*_sherpa_onnx*.pyd" | Select-Object -First 1
if (-not $SherpaRuntime) { throw "发行包缺少 sherpa-onnx Windows 运行库。" }
if ($SkipLaunch) { Write-Host "发行文件结构检查通过。"; return }

$Exe = Join-Path $ReleaseRoot "ADS会议智能体.exe"
$Process = Start-Process -FilePath $Exe -ArgumentList @("--port", "$Port", "--no-browser") -WorkingDirectory $ReleaseRoot -WindowStyle Hidden -PassThru
try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
            if ($Health.status -eq "ok") { $Ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw "发行版未在限定时间内通过健康检查。" }
    $HomepageResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 5
    if ($HomepageResponse.StatusCode -ne 200 -or $HomepageResponse.Headers."Content-Type" -notlike "text/html*" -or $HomepageResponse.Content -notmatch '<div id="root"></div>') {
        throw "发行版首页未正确加载前端页面。"
    }
    $Speech = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/speech/health" -TimeoutSec 30
    if ($Speech.status -ne "ready") { throw "发行版语音运行时未就绪：$($Speech.message)" }
    if (-not $Speech.diarization_available) { throw "发行版匿名说话人分离运行时未就绪：$($Speech.message)" }
    Write-Host "发行版启动、健康接口和本地语音检查通过。"
} finally {
    if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
}
