$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    throw "Run .\scripts\bootstrap.ps1 first."
}

$Npm = "C:\Program Files\nodejs\npm.cmd"
if (-not (Test-Path -LiteralPath $Npm)) {
    $Npm = (Get-Command npm -ErrorAction Stop).Source
}

$Api = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList @(
    "-m", "uvicorn", "werms_api.main:app", "--app-dir", "services/api/src", "--reload", "--port", "8000"
) -PassThru -WindowStyle Hidden

try {
    & $Npm run dev:web
}
finally {
    if (-not $Api.HasExited) {
        Stop-Process -Id $Api.Id
    }
}
