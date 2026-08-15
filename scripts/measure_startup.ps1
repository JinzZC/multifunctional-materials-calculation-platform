# Measure packaged EXE startup time (until its window appears).
# Uses a temp database via FT_DB_PATH; never touches real user data.
param([Parameter(Mandatory=$true)][string]$ExePath)
$ErrorActionPreference = 'Stop'
$verifyDb = Join-Path $env:TEMP 'fiber_verify.db'
Remove-Item $verifyDb -ErrorAction SilentlyContinue
$env:FT_DB_PATH = $verifyDb
$p = Start-Process -FilePath $ExePath -PassThru
$sw = [Diagnostics.Stopwatch]::StartNew()
do {
    Start-Sleep -Milliseconds 100
    $p.Refresh()          # Process 对象属性是缓存的，必须刷新
} while (-not $p.HasExited -and $p.MainWindowHandle -eq 0 -and $sw.ElapsedMilliseconds -lt 30000)
$sw.Stop()
$ms = $sw.ElapsedMilliseconds
if ($p.HasExited) {
    Write-Output ("startup_ms: FAILED (process exited, code " + $p.ExitCode + ")")
} else {
    Write-Output ("startup_ms: " + $ms)
    Stop-Process -Id $p.Id -Force
}
Write-Output ("db_created: " + (Test-Path $verifyDb))
