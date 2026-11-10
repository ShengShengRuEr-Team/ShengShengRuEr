$ErrorActionPreference = 'Stop'
$consoleDirectory = $PSScriptRoot
$repositoryDirectory = Split-Path (Split-Path $consoleDirectory -Parent) -Parent
$backendDirectory = if ($env:M3_CONSOLE_BACKEND_DIR) { $env:M3_CONSOLE_BACKEND_DIR } else { Join-Path $repositoryDirectory 'backend' }
$pythonExecutable = Join-Path $backendDirectory '.venv-api\Scripts\python.exe'
$serverScript = Join-Path $consoleDirectory 'server.py'
$consolePort = if ($env:M3_CONSOLE_PORT) { [int]$env:M3_CONSOLE_PORT } else { 8002 }
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Prepare backend/.venv-api using the module 3 setup guide first.' }
$listening = Get-NetTCPConnection -State Listen -LocalPort $consolePort -ErrorAction SilentlyContinue
if ($listening) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listening[0].OwningProcess)"
    if ($owner.CommandLine -notmatch [regex]::Escape($serverScript)) { throw "Port $consolePort belongs to another application. Set M3_CONSOLE_PORT to an unused port." }
    Write-Output "Already started: http://127.0.0.1:$consolePort/"
    exit 0
}
$consoleProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('"' + $serverScript + '"') -WorkingDirectory $backendDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $consoleDirectory 'server.stdout.log') -RedirectStandardError (Join-Path $consoleDirectory 'server.stderr.log') -PassThru
$consoleProcess.Id | Set-Content -LiteralPath (Join-Path $consoleDirectory 'server.pid') -Encoding utf8
Write-Output "Starting: http://127.0.0.1:$consolePort/ (see server.stderr.log if startup fails)"
