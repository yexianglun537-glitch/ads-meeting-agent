[CmdletBinding()]
param([string]$OutputDirectory = "submission")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = Join-Path $projectRoot $OutputDirectory
$stageRoot = Join-Path $outputRoot ".source-package-stage"
$packageRoot = Join-Path $stageRoot "ADS会议智能体源代码"
$zipPath = Join-Path $outputRoot "ADS会议智能体源代码.zip"

$files = @(
    ".gitignore",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "start-dev.cmd",
    "启动项目.bat",
    "backend/.env.example",
    "backend/requirements.txt",
    "frontend/index.html",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "packaging/ads-agent.spec",
    "packaging/build-release.ps1",
    "packaging/launcher.py",
    "packaging/requirements-build.txt",
    "packaging/verify-release.ps1",
    "docs/ADS核心Prompt与工作流说明.md",
    "docs/requirements/ADS会议智能体当前产品需求与验收标准.md",
    "docs/requirements/ADS会议智能体本地语音转文字工具需求文档.md",
    "docs/guides/ADS会议智能体使用教程.md",
    "docs/workflows/meeting-agent-workflow.yaml",
    "docs/workflows/meeting-analysis-output.schema.json"
)

$directories = @("backend/app", "backend/tests", "backend/tools", "frontend/src", "frontend/tests")

if (Test-Path -LiteralPath $stageRoot) {
    $resolvedStage = [IO.Path]::GetFullPath($stageRoot)
    $resolvedOutput = [IO.Path]::GetFullPath($outputRoot)
    if (-not $resolvedStage.StartsWith($resolvedOutput, [StringComparison]::OrdinalIgnoreCase)) {
        throw "临时目录不在输出目录内：$resolvedStage"
    }
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

foreach ($relativePath in $files) {
    $source = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "缺少打包文件：$relativePath" }
    $destination = Join-Path $packageRoot $relativePath
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

foreach ($relativePath in $directories) {
    $source = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "缺少打包目录：$relativePath" }
    $destination = Join-Path $packageRoot $relativePath
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
}

Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
    $_.Name -in @("__pycache__", ".pytest_cache") -or $_.Extension -eq ".pyc"
} | Sort-Object FullName -Descending | Remove-Item -Recurse -Force

$blocked = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
    $_.Name -in @(".env", "node_modules", ".venv", "__pycache__", ".pytest_cache") -or
    $_.Extension -in @(".db", ".sqlite", ".pyc", ".wav", ".mp3", ".mp4") -or
    $_.FullName -match "[\\/](backups|logs|dist|build|models|audio|tmp|\.tmp)[\\/]"
}
if ($blocked) { throw "源码包包含禁止内容：$($blocked.FullName -join ', ')" }

if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force

$zip = Get-Item -LiteralPath $zipPath
Write-Host "源码包已生成：$($zip.FullName)"
Write-Host "大小：$([math]::Round($zip.Length / 1MB, 2)) MB"
