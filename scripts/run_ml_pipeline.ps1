$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$taskDeadline = [DateTime]::UtcNow.AddHours(2)
Write-Output 'Waiting for the verified FireCastRL download manifest.'
while (-not (Test-Path -LiteralPath 'data/raw/firecastrl/Wildfire_Dataset.csv.manifest.json')) {
    if ([DateTime]::UtcNow -gt $taskDeadline) { throw 'Dataset download has not completed.' }
    Start-Sleep -Seconds 2
}
$taskPrepare = $true
if (Test-Path -LiteralPath 'data/processed/firecastrl-v1/manifest.json') {
    $taskPrepared = Get-Content -Raw 'data/processed/firecastrl-v1/manifest.json' | ConvertFrom-Json
    $taskDownloaded = Get-Content -Raw 'data/raw/firecastrl/Wildfire_Dataset.csv.manifest.json' | ConvertFrom-Json
    $taskPrepare = $taskPrepared.sha256 -ne $taskDownloaded.sha256
}
if ($taskPrepare) {
    & $taskPython -m ml.prepare
    if ($LASTEXITCODE -ne 0) { throw 'Dataset audit or sequence preparation failed.' }
}
Write-Output 'Causal sequences prepared.'
$taskTorchVersion = & $taskPython -c "import importlib.metadata; print(next((d.version for d in importlib.metadata.distributions() if d.metadata['Name']=='torch'),'missing'))"
if (-not $taskTorchVersion.StartsWith('2.6.0')) {
    Write-Output 'Waiting for verified PyTorch wheel.'
    while (-not (Test-Path -LiteralPath 'tmp/ml-wheels/torch-2.6.0-cp312-cp312-win_amd64.whl.manifest.json')) {
        if ([DateTime]::UtcNow -gt $taskDeadline) { throw 'PyTorch download has not completed.' }
        Start-Sleep -Seconds 2
    }
    & $taskPython -m pip install --no-index --find-links tmp/ml-wheels torch==2.6.0
    if ($LASTEXITCODE -ne 0) { throw 'Offline PyTorch installation failed.' }
}
if (Test-Path -LiteralPath 'artifacts/models/firecastrl-v1/report.json') {
    $taskExistingRun = Get-Content -Raw 'artifacts/models/firecastrl-v1/report.json' | ConvertFrom-Json
    $taskDownloaded = Get-Content -Raw 'data/raw/firecastrl/Wildfire_Dataset.csv.manifest.json' | ConvertFrom-Json
    if ($taskExistingRun.dataset.sha256 -ne $taskDownloaded.sha256) { throw 'Existing immutable run uses another source. Train with a new --output directory.' }
    Write-Output 'Reusing completed immutable experiment; choose a new ml.train --output for another run.'
} else {
    & $taskPython -m ml.train --epochs 12
    if ($LASTEXITCODE -ne 0) { throw 'Model comparison failed; no evaluated result was published.' }
}
Copy-Item -LiteralPath 'artifacts/models/firecastrl-v1/report.json' -Destination 'docs/benchmarks/firecastrl-run.json'
Write-Output 'Verified experiment report saved to docs/benchmarks/firecastrl-run.json.'
