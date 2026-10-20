$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Python = "C:\Users\hp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Npm = "C:\Program Files\nodejs\npm.cmd"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $Npm)) {
    $Npm = (Get-Command npm -ErrorAction Stop).Source
}

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath ".venv")) {
    & $Python -m venv .venv
}

Invoke-Checked { & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip }
Invoke-Checked { & ".\.venv\Scripts\python.exe" -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu }
Invoke-Checked { & ".\.venv\Scripts\python.exe" -m pip install -e ".\services\api[dev,ml,spatial]" }
Invoke-Checked { & $Npm install }

Write-Host "WERMS environment is ready. Run .\scripts\dev.ps1"
