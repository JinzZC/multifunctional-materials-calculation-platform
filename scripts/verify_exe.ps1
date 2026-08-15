# Verify the packaged EXE: launch it against a TEMP database (never touches
# the user's real data in %LOCALAPPDATA%\FiberTensile), confirm it stays
# alive, then close.
$ErrorActionPreference = 'Stop'
$verifyDb = Join-Path $env:TEMP 'fiber_verify.db'
Remove-Item $verifyDb -ErrorAction SilentlyContinue
$env:FT_DB_PATH = $verifyDb          # child process inherits this
$p = Start-Process -FilePath 'dist\FiberTensileAnalyzer\FiberTensileAnalyzer.exe' -PassThru
Start-Sleep -Seconds 15
$alive = -not $p.HasExited
Write-Output ("process_alive: " + $alive)
if ($alive) {
    Stop-Process -Id $p.Id -Force
    Write-Output 'process_stopped'
}
Write-Output ("db_created: " + (Test-Path $verifyDb))
