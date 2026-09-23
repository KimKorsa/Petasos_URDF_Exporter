$ErrorActionPreference = "SilentlyContinue"

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$entryPoint = [IO.Path]::GetFullPath((Join-Path $projectRoot "petasos_standalone.py"))
$entryPattern = [regex]::Escape($entryPoint)
$currentPid = $PID

$targets = @(
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object {
            $_.ProcessId -ne $currentPid -and
            $_.CommandLine -and
            $_.CommandLine -match $entryPattern
        } |
        Sort-Object ProcessId -Descending
)

if ($targets.Count -eq 0) {
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
}

$deadline = [DateTime]::UtcNow.AddSeconds(3)
do {
    $remaining = @(
        Get-Process -Id $targets.ProcessId -ErrorAction SilentlyContinue
    )
    if ($remaining.Count -eq 0) {
        break
    }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)

Write-Host "Previous Petasos server closed."
exit 0
