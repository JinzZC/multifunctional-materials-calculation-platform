# Verify the packaged EXE: launch it against a TEMP database (never touches
# the user's real data), confirm it stays alive, then close.
# The folder-version EXE is auto-discovered (dist\<folder>\<folder>.exe),
# so this script stays ASCII-only and works with Chinese EXE names.
$ErrorActionPreference = 'Stop'
$folderExe = $null
foreach ($dir in Get-ChildItem -Path 'dist' -Directory) {
    $candidate = Get-ChildItem -Path $dir.FullName -Filter '*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { $folderExe = $candidate.FullName; break }
}
if (-not $folderExe) { Write-Output 'NO_EXE_FOUND'; exit 1 }
Write-Output ("exe: " + $folderExe)
$verifyDb = Join-Path $env:TEMP 'fiber_verify.db'
Remove-Item $verifyDb -ErrorAction SilentlyContinue
$env:FT_DB_PATH = $verifyDb          # child process inherits this
$p = Start-Process -FilePath $folderExe -PassThru
Start-Sleep -Seconds 15
$alive = -not $p.HasExited
Write-Output ("process_alive: " + $alive)
if ($alive) {
    Stop-Process -Id $p.Id -Force
    Write-Output 'process_stopped'
}
Write-Output ("db_created: " + (Test-Path $verifyDb))
