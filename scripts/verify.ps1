$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Npm = "C:\Program Files\nodejs\npm.cmd"
if (-not (Test-Path -LiteralPath $Npm)) {
    $Npm = (Get-Command npm -ErrorAction Stop).Source
}

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Verification command failed with exit code $LASTEXITCODE"
    }
}

Invoke-Checked { & ".\.venv\Scripts\python.exe" -m ruff check services/api }
$TestParent = Join-Path $ProjectRoot "tmp/verification"
New-Item -ItemType Directory -Path $TestParent -Force | Out-Null
$TestTemp = Join-Path $TestParent ([guid]::NewGuid().ToString("N"))
Invoke-Checked { & ".\.venv\Scripts\python.exe" -m pytest services/api/tests --basetemp $TestTemp -p no:cacheprovider --tb=short }
Invoke-Checked { & $Npm run lint:web }
Invoke-Checked { & $Npm run test:web }
Invoke-Checked { & $Npm run build:web }
