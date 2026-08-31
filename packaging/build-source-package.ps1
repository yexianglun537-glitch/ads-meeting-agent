[CmdletBinding()]
param([string]$OutputDirectory = "submission")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = Join-Path $projectRoot $OutputDirectory
$stageRoot = Join-Path $outputRoot ".source-package-stage"
$packageRoot = Join-Path $stageRoot "ADS会议智能体源代码"
$zipPath = Join-Path $outputRoot "04- ADS会议智能体源代码.zip"
$python = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$coreRequirements = Join-Path $projectRoot "backend\requirements-core.txt"
$frontend = Join-Path $projectRoot "frontend"
$frontendDist = Join-Path $frontend "dist"

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "命令失败：$Program $($Arguments -join ' ')" }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "缺少打包用 Python：$python" }

Invoke-Checked "npm.cmd" @("test") $frontend
Invoke-Checked "npm.cmd" @("run", "typecheck") $frontend
Invoke-Checked "npm.cmd" @("run", "build") $frontend
if (-not (Test-Path -LiteralPath (Join-Path $frontendDist "index.html") -PathType Leaf)) {
    throw "前端生产构建结果缺失：frontend/dist/index.html"
}

$files = @(
    ".gitignore",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "start-dev.cmd",
    "启动项目.bat",
    "backend/.env.example",
    "backend/requirements-core.txt",
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
    "docs/README.md",
    "docs/ADS核心Prompt与工作流说明.md",
    "docs/requirements/2026-08-31-源码包兼容性交付要求.md",
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

Copy-Item -LiteralPath $frontendDist -Destination (Join-Path $packageRoot "frontend\dist") -Recurse

$wheelhouse = Join-Path $packageRoot "backend\wheelhouse"
New-Item -ItemType Directory -Path $wheelhouse -Force | Out-Null
$targets = @(
    @{ Version = "311"; Abi = "cp311" },
    @{ Version = "312"; Abi = "cp312" },
    @{ Version = "313"; Abi = "cp313" },
    @{ Version = "314"; Abi = "cp314" }
)
foreach ($target in $targets) {
    & $python -m pip download `
        --dest $wheelhouse `
        --requirement $coreRequirements `
        --only-binary=:all: `
        --platform win_amd64 `
        --implementation cp `
        --python-version $target.Version `
        --abi $target.Abi
    if ($LASTEXITCODE -ne 0) { throw "源码包离线依赖下载失败：$($target.Abi)" }
}

foreach ($target in $targets) {
    foreach ($package in @("pydantic_core", "charset_normalizer")) {
        $pattern = "$package-*-$($target.Abi)-$($target.Abi)-win_amd64.whl"
        if (-not (Get-ChildItem -LiteralPath $wheelhouse -File -Filter $pattern)) {
            throw "源码包缺少离线 wheel：$pattern"
        }
    }
}

$wheelFiles = Get-ChildItem -LiteralPath $wheelhouse -File
if ($wheelFiles.Extension -ne ".whl") { throw "源码包离线依赖中存在非 wheel 文件" }
$wheelBytes = ($wheelFiles | Measure-Object -Property Length -Sum).Sum
Write-Host "离线 wheel：$($wheelFiles.Count) 个，$([math]::Round($wheelBytes / 1MB, 2)) MB"

Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
    $_.Name -in @("__pycache__", ".pytest_cache") -or $_.Extension -eq ".pyc"
} | Sort-Object FullName -Descending | Remove-Item -Recurse -Force

$blocked = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
    $item = $_
    $relativePath = [IO.Path]::GetRelativePath($packageRoot, $item.FullName)
    $item.Name -in @(".env", "node_modules", ".venv", "__pycache__", ".pytest_cache") -or
    $item.Extension -in @(".db", ".sqlite", ".pyc", ".wav", ".mp3", ".mp4") -or
    ($relativePath -notmatch "^frontend[\\/]dist([\\/]|$)" -and
        $relativePath -match "(^|[\\/])(backups|logs|dist|build|models|audio|tmp|\.tmp)([\\/]|$)")
}
if ($blocked) { throw "源码包包含禁止内容：$($blocked.FullName -join ', ')" }

if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force

$zip = Get-Item -LiteralPath $zipPath
Write-Host "源码包已生成：$($zip.FullName)"
Write-Host "大小：$([math]::Round($zip.Length / 1MB, 2)) MB"
