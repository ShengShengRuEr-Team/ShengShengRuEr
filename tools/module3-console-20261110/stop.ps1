$ErrorActionPreference = 'Stop'
$consolePort = if ($env:M3_CONSOLE_PORT) { [int]$env:M3_CONSOLE_PORT } else { 8002 }
$listener = Get-NetTCPConnection -State Listen -LocalPort $consolePort -ErrorAction SilentlyContinue
if (-not $listener) { Write-Output "No listener on port $consolePort."; exit 0 }
$consoleProcessId = $listener[0].OwningProcess
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$consoleProcessId"
$serverScript = Join-Path $PSScriptRoot 'server.py'
if ($processInfo.CommandLine -notmatch [regex]::Escape($serverScript)) { throw 'Port belongs to another application. Nothing was stopped.' }
$dataDirectory = if ($env:M3_CONSOLE_DATA_DIR) { $env:M3_CONSOLE_DATA_DIR } else { Join-Path $PSScriptRoot 'data' }
$workerPidFile = Join-Path $dataDirectory 'logs\worker.pid'
if (Test-Path -LiteralPath $workerPidFile) {
    $workerProcessId = [int](Get-Content -LiteralPath $workerPidFile)
    $workerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$workerProcessId"
    $workerScript = Join-Path $PSScriptRoot 'console_worker.py'
    if ($workerInfo -and $workerInfo.CommandLine -match [regex]::Escape($workerScript)) {
        & taskkill.exe /PID $workerProcessId /T /F
    }
}
& taskkill.exe /PID $consoleProcessId /T /F
