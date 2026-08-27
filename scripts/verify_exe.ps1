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
$verifyRoot = Join-Path $env:TEMP ("fiber-verify-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verifyRoot | Out-Null
$verifyDb = Join-Path $verifyRoot 'fiber_verify.db'
$env:FT_DB_PATH = $verifyDb          # child process inherits this
$p = Start-Process -FilePath $folderExe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 15
$p.Refresh()
$alive = -not $p.HasExited
Write-Output ("process_alive: " + $alive)
Write-Output ("window_title: " + $p.MainWindowTitle)
if ($alive) {
    Stop-Process -Id $p.Id -Force
    Write-Output 'process_stopped'
}
$dbCreated = Test-Path $verifyDb
Write-Output ("db_created: " + $dbCreated)
Remove-Item Env:FT_DB_PATH -ErrorAction SilentlyContinue
if (-not $alive -or -not $dbCreated -or $p.MainWindowTitle -eq 'Unhandled exception in script') {
    exit 1
}
