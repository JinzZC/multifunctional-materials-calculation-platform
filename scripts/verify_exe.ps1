# Verify both packaged variants against synthetic data and temporary settings.
param([string]$ExePath)
$ErrorActionPreference = 'Stop'
$executables = @()
if ($ExePath) {
    $executables = @((Resolve-Path -LiteralPath $ExePath).Path)
} else {
    foreach ($dir in Get-ChildItem -LiteralPath 'dist' -Directory) {
        $candidate = Join-Path $dir.FullName ($dir.Name + '.exe')
        if (Test-Path -LiteralPath $candidate) { $executables += $candidate }
    }
    $executables += @(Get-ChildItem -LiteralPath 'dist' -Filter '*.exe' -File | ForEach-Object { $_.FullName })
}
if ($executables.Count -eq 0) { throw 'NO_EXE_FOUND' }
$verifyRoot = Join-Path $env:TEMP ('fiber-package-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verifyRoot | Out-Null
foreach ($executable in $executables) {
    $resultFile = Join-Path $verifyRoot ([guid]::NewGuid().ToString('N') + '.json')
    $process = Start-Process -FilePath $executable -ArgumentList @('--verify-package', ('"' + $resultFile + '"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(90000)) {
        Stop-Process -Id $process.Id -Force
        throw ('Verification timed out: ' + $executable)
    }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $resultFile)) {
        throw ('Verification failed: ' + $executable)
    }
    $result = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
    if (-not $result.database_isolated -or -not $result.settings_isolated -or $result.navigation -ne 6 -or $result.exports.Count -ne 3) {
        throw ('Incomplete verification: ' + $executable)
    }
    Write-Output ('VERIFIED: ' + $executable)
    Get-Content -LiteralPath $resultFile
}
