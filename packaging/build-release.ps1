[CmdletBinding()]
param([string]$Version = "0.1.0")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
$Frontend = Join-Path $ProjectRoot "frontend"
$DistRoot = Join-Path $ProjectRoot "dist"
$ReleaseDir = Join-Path $DistRoot "ADS会议智能体"
$ZipPath = Join-Path $DistRoot "ADS会议智能体-$Version-win64.zip"

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "命令失败：$Program $($Arguments -join ' ')" }
    } finally { Pop-Location }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "未找到项目 Python：$Python" }
Invoke-Checked "npm.cmd" @("test") $Frontend
Invoke-Checked "npm.cmd" @("run", "typecheck") $Frontend
Invoke-Checked "npm.cmd" @("run", "build") $Frontend
Invoke-Checked $Python @("-m", "pytest", "tests", "-q") (Join-Path $ProjectRoot "backend")
Invoke-Checked $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $DistRoot, "--workpath", (Join-Path $ProjectRoot "build\pyinstaller"), (Join-Path $ProjectRoot "packaging\ads-agent.spec")) $ProjectRoot

if (-not (Test-Path -LiteralPath $ReleaseDir -PathType Container)) { throw "PyInstaller 未生成发行目录：$ReleaseDir" }
& (Join-Path $ProjectRoot "packaging\verify-release.ps1") -ReleaseDir $ReleaseDir -SkipLaunch
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -LiteralPath $ReleaseDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "发行包已生成：$ZipPath"
