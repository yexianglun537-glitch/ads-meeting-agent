$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$envFile = Join-Path $backend ".env"
$envExample = Join-Path $backend ".env.example"
$depsMarker = Join-Path $backend ".venv\.deps-installed"
$logs = Join-Path $root "logs"
$backendLog = Join-Path $logs "backend.log"
$frontendLog = Join-Path $logs "frontend.log"

function Write-Step($message) {
    Write-Host ""
    Write-Host "== $message" -ForegroundColor Cyan
}

function Test-Command($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Receive-RecentJobOutput($job, $count = 8) {
    Receive-Job -Job $job -Keep -ErrorAction SilentlyContinue | Select-Object -Last $count
}

function Test-HttpReady($url) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-HttpReady($url, $name, $job, $seconds = 45) {
    for ($i = 0; $i -lt $seconds; $i++) {
        Start-Sleep -Seconds 1
        if ($job.State -ne "Running") {
            Write-Host ""
            Write-Host "$name stopped before it became ready." -ForegroundColor Red
            Receive-RecentJobOutput $job 20
            throw "$name failed to start. See logs for details."
        }
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return
        } catch {
            if (($i + 1) % 10 -eq 0) {
                Write-Host "Waiting for $name..."
                Receive-RecentJobOutput $job 3
            }
        }
    }
    Write-Host ""
    Write-Host "$name was not ready within $seconds seconds." -ForegroundColor Red
    Receive-RecentJobOutput $job 20
    throw "$name was not ready. See logs for details."
}

Write-Step "Checking runtime"
if (-not (Test-Command "python")) {
    throw "python was not found. Install Python 3.11+ and make sure it is on PATH."
}
if (-not (Test-Command "npm")) {
    throw "npm was not found. Install Node.js 20+."
}

Write-Step "Preparing backend"
if (-not (Test-Path $python)) {
    Push-Location $backend
    python -m venv .venv
    Pop-Location
}

if (-not (Test-Path $envFile)) {
    Copy-Item -Path $envExample -Destination $envFile
}

if (-not (Test-Path $depsMarker)) {
    Push-Location $backend
    & $python -m pip install -r requirements.txt
    New-Item -ItemType File -Force -Path $depsMarker | Out-Null
    Pop-Location
}

Write-Step "Preparing frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    npm install
    Pop-Location
}

if (-not (Test-Path $logs)) {
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
}

Write-Step "Starting services"
$backendJob = $null
$frontendJob = $null

if (Test-HttpReady "http://127.0.0.1:8000/api/health") {
    Write-Host "Backend is already running; reusing it." -ForegroundColor Yellow
} else {
    $backendJob = Start-Job -Name "ads-meeting-agent-backend" -ScriptBlock {
        param($backendPath, $logPath)
        Set-Location $backendPath
        & ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath $logPath -Append
    } -ArgumentList $backend, $backendLog
}

if (Test-HttpReady "http://127.0.0.1:5173") {
    Write-Host "Frontend is already running; reusing it." -ForegroundColor Yellow
} else {
    $frontendJob = Start-Job -Name "ads-meeting-agent-frontend" -ScriptBlock {
        param($frontendPath, $logPath)
        Set-Location $frontendPath
        npm run dev -- --host 127.0.0.1 2>&1 | Tee-Object -FilePath $logPath -Append
    } -ArgumentList $frontend, $frontendLog
}

try {
    if ($backendJob) {
        Wait-HttpReady "http://127.0.0.1:8000/api/health" "Backend" $backendJob 45
    }
    if ($frontendJob) {
        Wait-HttpReady "http://127.0.0.1:5173" "Frontend" $frontendJob 45
    }

    Write-Host ""
    Write-Host "Started:" -ForegroundColor Green
    Write-Host "Backend http://127.0.0.1:8000"
    Write-Host "Frontend http://127.0.0.1:5173"
    Write-Host "Logs    $logs"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both services."
    try {
        Start-Process "http://127.0.0.1:5173" -ErrorAction Stop
    } catch {
        Write-Warning "Could not open the browser automatically. Open http://127.0.0.1:5173 manually."
    }

    while ($true) {
        if ($backendJob -and $backendJob.State -ne "Running") {
            Receive-RecentJobOutput $backendJob 20
            throw "Backend stopped unexpectedly."
        }
        if ($frontendJob -and $frontendJob.State -ne "Running") {
            Receive-RecentJobOutput $frontendJob 20
            throw "Frontend stopped unexpectedly."
        }
        if ($backendJob) {
            Receive-RecentJobOutput $backendJob 5
        }
        if ($frontendJob) {
            Receive-RecentJobOutput $frontendJob 5
        }
        Start-Sleep -Seconds 3
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping services..."
    $startedJobs = @($backendJob, $frontendJob) | Where-Object { $null -ne $_ }
    if ($startedJobs.Count -gt 0) {
        Stop-Job -Job $startedJobs -ErrorAction SilentlyContinue
        Remove-Job -Job $startedJobs -Force -ErrorAction SilentlyContinue
    }
}
