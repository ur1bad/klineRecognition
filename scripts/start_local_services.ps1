param(
    [switch]$RestartExisting
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendPort = 8000
$FrontendPort = 8501
$RemoteApiBaseUrl = "https://u950557-5mw7-915677dc.bjb1.seetacloud.com:8443"
$PythonExe = "python"

$TmpDir = Join-Path $ProjectRoot "outputs\tmp"
$BackendStdout = Join-Path $TmpDir "backend.stdout.log"
$BackendStderr = Join-Path $TmpDir "backend.stderr.log"
$FrontendStdout = Join-Path $TmpDir "streamlit.stdout.log"
$FrontendStderr = Join-Path $TmpDir "streamlit.stderr.log"

function Get-PortPid([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $connection) {
        return $null
    }
    return [int]$connection.OwningProcess
}

function Stop-PortProcess([int]$Port) {
    $portProcessId = Get-PortPid -Port $Port
    if ($null -ne $portProcessId) {
        try {
            Stop-Process -Id $portProcessId -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
            Write-Host "Stopped process on port ${Port}: PID ${portProcessId}"
        } catch {
            Write-Host "Failed to stop process on port ${Port}: PID ${portProcessId}"
            throw
        }
    }
}

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

if ($RestartExisting) {
    Stop-PortProcess -Port $BackendPort
    Stop-PortProcess -Port $FrontendPort
}

$backendExistingPid = Get-PortPid -Port $BackendPort
$frontendExistingPid = Get-PortPid -Port $FrontendPort

$env:KLINE_INFERENCE_BACKEND = "remote_api"
$env:KLINE_REMOTE_API_PROTOCOL = "custom_fastapi"
$env:KLINE_REMOTE_API_BASE_URL = $RemoteApiBaseUrl
$env:KLINE_REMOTE_API_PREDICT_PATH = "/predict"
$env:KLINE_REMOTE_API_HEALTH_PATH = "/health"
$env:KLINE_REMOTE_API_DISPLAY_NAME = "Qwen2.5-VL-7B-Instruct"
$env:KLINE_MODEL_MAX_NEW_TOKENS = "160"
$env:KLINE_MODEL_TEMPERATURE = "0.0"
$env:STREAMLIT_BACKEND_URL = "http://127.0.0.1:${BackendPort}"

if ($null -eq $backendExistingPid) {
    Set-Content -Path $BackendStdout -Value ""
    Set-Content -Path $BackendStderr -Value ""
    Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $BackendStdout `
        -RedirectStandardError $BackendStderr `
        -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 4
    Write-Host "Backend started on http://127.0.0.1:${BackendPort}"
} else {
    Write-Host "Backend already listening on port ${BackendPort}. PID: ${backendExistingPid}"
}

if ($null -eq $frontendExistingPid) {
    Set-Content -Path $FrontendStdout -Value ""
    Set-Content -Path $FrontendStderr -Value ""
    Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "streamlit", "run", "streamlit_app.py", "--server.headless", "true", "--server.port", "$FrontendPort") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $FrontendStdout `
        -RedirectStandardError $FrontendStderr `
        -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 6
    Write-Host "Frontend started on http://127.0.0.1:${FrontendPort}"
} else {
    Write-Host "Frontend already listening on port ${FrontendPort}. PID: ${frontendExistingPid}"
}

try {
    $health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:${BackendPort}/health" | Select-Object -ExpandProperty Content
    Write-Host ""
    Write-Host "Backend health:"
    Write-Host $health
} catch {
    Write-Host ""
    Write-Host "Backend health check failed. Check log:"
    Write-Host $BackendStderr
}

Write-Host ""
Write-Host "Remote model service:"
Write-Host $RemoteApiBaseUrl
Write-Host ""
Write-Host "Frontend:"
Write-Host "http://127.0.0.1:${FrontendPort}"
Write-Host ""
Write-Host "Logs:"
Write-Host $BackendStdout
Write-Host $BackendStderr
Write-Host $FrontendStdout
Write-Host $FrontendStderr
Write-Host ""
Write-Host "If the AutoDL public URL changes, edit this file and update:"
Write-Host '$RemoteApiBaseUrl'

