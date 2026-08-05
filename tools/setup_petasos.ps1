# PETASOS_SETUP_VERSION=2026.08.03.20
param(
    [switch]$CheckOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:WSL_UTF8 = "1"
& chcp.com 65001 *> $null

$setupMutex = [System.Threading.Mutex]::new(
    $false,
    "Local\PetasosA2Setup"
)
try {
    $setupLockAcquired = $setupMutex.WaitOne(0, $false)
}
catch [System.Threading.AbandonedMutexException] {
    $setupLockAcquired = $true
}
if (-not $setupLockAcquired) {
    Write-Host "Another Petasos setup is already running." -ForegroundColor Yellow
    Write-Host "Keep the existing setup window open and close this duplicate window."
    exit 4
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvRoot = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "requirements-standalone.txt"
$SupportedPythonMin = [version]"3.10"
$SupportedPythonMax = [version]"3.14"

function Write-Check {
    param(
        [string]$Label,
        [bool]$Ok,
        [string]$Detail
    )
    $oldColor = $Host.UI.RawUI.ForegroundColor
    try {
        $Host.UI.RawUI.ForegroundColor = if ($Ok) { "Green" } else { "Yellow" }
        $mark = if ($Ok) { "[OK]" } else { "[CHECK]" }
        Write-Host ("{0} {1}" -f $mark, $Label)
    }
    finally {
        $Host.UI.RawUI.ForegroundColor = $oldColor
    }
    if ($Detail) {
        Write-Host ("     {0}" -f $Detail)
    }
}

function Get-PythonVersion {
    param([string]$Executable)
    try {
        $text = & $Executable -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $text) {
            return $null
        }
        return [version]($text | Select-Object -First 1)
    }
    catch {
        return $null
    }
}

function Find-SafeBasePython {
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($relative in @(
        "anaconda3\python.exe",
        "miniconda3\python.exe",
        "AppData\Local\Programs\Python\Python313\python.exe",
        "AppData\Local\Programs\Python\Python312\python.exe",
        "AppData\Local\Programs\Python\Python311\python.exe",
        "AppData\Local\Programs\Python\Python310\python.exe"
    )) {
        $candidates.Add((Join-Path $env:USERPROFILE $relative))
    }
    try {
        $command = Get-Command python.exe -ErrorAction Stop
        if ($command.Source) {
            $candidates.Add($command.Source)
        }
    }
    catch {
        # Python not being on PATH is a normal diagnostic result.
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $version = Get-PythonVersion $candidate
        if ($null -ne $version -and $version -ge $SupportedPythonMin -and $version -lt $SupportedPythonMax) {
            return [pscustomobject]@{
                Path = $candidate
                Version = $version
            }
        }
    }
    return $null
}

function Test-PetasosPython {
    param([string]$Executable)
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return [pscustomobject]@{
            Ready = $false
            Detail = "The project-local Python environment does not exist yet."
        }
    }
    $version = Get-PythonVersion $Executable
    if ($null -eq $version) {
        return [pscustomobject]@{
            Ready = $false
            Detail = "The .venv Python cannot run. The existing folder was not deleted."
        }
    }
    $missingModules = New-Object System.Collections.Generic.List[string]
    foreach ($moduleName in @("flask", "trimesh", "numpy", "scipy", "OCP")) {
        try {
            $moduleProbe = "import importlib; importlib.import_module('$moduleName')"
            & $Executable -c $moduleProbe 2>$null
            if ($LASTEXITCODE -ne 0) {
                $missingModules.Add($moduleName)
            }
        }
        catch {
            $missingModules.Add($moduleName)
        }
    }
    $missingText = $missingModules -join ","
    return [pscustomobject]@{
        Ready = [string]::IsNullOrWhiteSpace($missingText)
        Detail = if ([string]::IsNullOrWhiteSpace($missingText)) {
            "Python $version - required packages are ready"
        } else {
            "Missing or unusable Python modules: $missingText"
        }
    }
}

function Test-Inventor {
    try {
        $type = [type]::GetTypeFromProgID("Inventor.Application")
        return ($null -ne $type)
    }
    catch {
        return $false
    }
}

function Test-WslRos {
    $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($null -eq $wslCommand) {
        return [pscustomobject]@{
            Wsl = $false
            Distro = $false
            Ros = $false
            Detail = "WSL is not installed. It is optional for the Petasos editor."
        }
    }

    $hasDistro = $false
    try {
        $distroOutput = & wsl.exe --list --quiet 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($line in $distroOutput) {
                $name = (([string]$line) -replace "`0", "").TrimStart([char]0xFEFF).Trim()
                if ($name -eq "Ubuntu-22.04") {
                    $hasDistro = $true
                    break
                }
            }
        }
    }
    catch {
        $hasDistro = $false
    }
    if (-not $hasDistro) {
        return [pscustomobject]@{
            Wsl = $true
            Distro = $false
            Ros = $false
            Detail = "WSL exists, but the Ubuntu-22.04 distribution is missing."
        }
    }

    $rosReady = $false
    try {
        & wsl.exe -d Ubuntu-22.04 -- bash -lc (
            "test -f /opt/ros/humble/setup.bash && " +
            "source /opt/ros/humble/setup.bash && " +
            "ros2 pkg prefix rviz2 >/dev/null && " +
            "ros2 pkg prefix joint_state_publisher_gui >/dev/null && " +
            "ros2 pkg prefix moveit_setup_assistant >/dev/null && " +
            "ros2 pkg prefix moveit_ros_move_group >/dev/null && " +
            "ros2 pkg prefix controller_manager >/dev/null && " +
            "ros2 pkg prefix joint_state_broadcaster >/dev/null && " +
            "ros2 pkg prefix joint_trajectory_controller >/dev/null && " +
            "ros2 pkg prefix gazebo_ros >/dev/null && " +
            "command -v colcon >/dev/null && " +
            "command -v rosdep >/dev/null && " +
            "command -v xacro >/dev/null"
        ) *> $null
        $rosReady = ($LASTEXITCODE -eq 0)
    }
    catch {
        $rosReady = $false
    }

    return [pscustomobject]@{
        Wsl = $true
        Distro = $true
        Ros = $rosReady
        Detail = if ($rosReady) {
            "Ubuntu-22.04 - Humble - RViz - MoveIt - ros2_control - Gazebo - colcon are ready"
        } else {
            "Ubuntu-22.04 exists, but the ROS 2/RViz/MoveIt control toolchain is incomplete."
        }
    }
}

function Install-LocalEnvironment {
    param([pscustomobject]$BasePython)
    if ($null -eq $BasePython) {
        throw (
            "Python 3.10 through 3.13 was not found. Install Python first, " +
            "then run this helper again."
        )
    }
    if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
        throw "requirements-standalone.txt was not found."
    }

    if (Test-Path -LiteralPath $VenvRoot -PathType Container) {
        $existingVenvVersion = Get-PythonVersion $VenvPython
        if ($null -eq $existingVenvVersion) {
            # Python virtual environments contain an absolute reference to the
            # computer that created them and therefore cannot be copied between
            # PCs. Preserve the stale folder instead of deleting it, then build
            # a clean environment with this computer's verified base Python.
            $backupSuffix = Get-Date -Format "yyyyMMdd-HHmmss"
            $backupPath = Join-Path $ProjectRoot ".venv.petasos-backup-$backupSuffix"
            Write-Host ""
            Write-Host "The copied or damaged .venv belongs to another Python installation." -ForegroundColor Yellow
            Write-Host "Moving it aside without deleting it: $backupPath"
            Move-Item -LiteralPath $VenvRoot -Destination $backupPath
        }
    }

    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        Write-Host ""
        Write-Host "[1/3] Creating the project-local .venv..." -ForegroundColor Cyan
        & $BasePython.Path -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create .venv."
        }
    }

    Write-Host ""
    Write-Host "[2/3] Installing Petasos Python packages inside .venv..." -ForegroundColor Cyan
    Write-Host "Downloads may finish first; unpacking CAD packages can then be quiet for several minutes."
    if ($ProjectRoot -match "(?i)[\\/]OneDrive[\\/]") {
        Write-Host "OneDrive is scanning this .venv, so this stage may be considerably slower." -ForegroundColor Yellow
        Write-Host "Keep this window open while progress heartbeats continue."
    }

    $quotedRequirements = '"{0}"' -f $Requirements.Replace('"', '\"')
    $pipProcess = Start-Process `
        -FilePath $VenvPython `
        -ArgumentList @(
            "-m", "pip", "install",
            "--disable-pip-version-check",
            "-r", $quotedRequirements
        ) `
        -NoNewWindow `
        -PassThru
    $installTimer = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $pipProcess.WaitForExit(10000)) {
        $elapsed = $installTimer.Elapsed.ToString('hh\:mm\:ss')
        Write-Host "[2/3] Still installing Python/CAD packages... elapsed $elapsed" -ForegroundColor DarkCyan
    }
    $installTimer.Stop()
    $pipProcess.WaitForExit()
    $pipProcess.Refresh()
    $installElapsed = $installTimer.Elapsed.ToString('hh\:mm\:ss')
    $pipExitCode = $pipProcess.ExitCode
    if ($pipExitCode -ne 0) {
        Write-Host (
            "[2/3] pip reported exit code $pipExitCode after package installation. " +
            "Checking the installed environment before treating it as a failure..."
        ) -ForegroundColor Yellow
        $installedState = Test-PetasosPython $VenvPython
        & $VenvPython -m pip check
        $pipCheckOk = ($LASTEXITCODE -eq 0)
        if (-not $installedState.Ready -or -not $pipCheckOk) {
            throw (
                "Failed to install Python packages (pip exit code $pipExitCode). " +
                $installedState.Detail
            )
        }
        Write-Host (
            "[2/3] Required imports and dependency checks passed; " +
            "continuing despite the stale pip exit code."
        ) -ForegroundColor Green
    }
    Write-Host "[2/3] Package installation completed in $installElapsed." -ForegroundColor Green
    Write-Host "[3/3] Verifying Flask, numerical, mesh, and OpenCascade modules..." -ForegroundColor Cyan
}

function Show-PythonInstallGuide {
    Write-Host ""
    Write-Host "Required first step: install 64-bit Python 3.12 or 3.13." -ForegroundColor Cyan
    Write-Host "Python 3.12 is recommended for the broadest Petasos package compatibility."
    Write-Host "Official download page: https://www.python.org/downloads/windows/"
    Write-Host "After Python installation finishes, close this window and run setup_petasos.cmd again."
    Write-Host "Petasos will then create only this project-local environment: $ProjectRoot\.venv"
    if ($CheckOnly) {
        return
    }
    $answer = Read-Host "Open the official Python download page now? (Y/N)"
    if ($answer -match "^[Yy]$") {
        Start-Process "https://www.python.org/downloads/windows/"
    }
}

function Install-CompatiblePythonWithWinget {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        Write-Host ""
        Write-Host "Windows Package Manager (winget) is not available." -ForegroundColor Yellow
        Write-Host "Petasos will show the official Python download guide instead."
        return $false
    }

    Write-Host ""
    Write-Host "Python 3.12 can be installed automatically for the current Windows user." -ForegroundColor Cyan
    Write-Host "This adds Python to Windows Installed Apps, but does not require administrator rights."
    Write-Host "Petasos packages will still be installed only inside: $ProjectRoot\.venv"
    $answer = Read-Host "Install Python 3.12 automatically for the current Windows user? (Y/N)"
    if ($answer -notmatch "^[Yy]$") {
        Write-Host "Skipped automatic Python installation."
        return $false
    }

    Write-Host ""
    Write-Host "Installing Python 3.12 with Windows Package Manager..."
    & $winget.Source install `
        --id Python.Python.3.12 `
        --exact `
        --source winget `
        --scope user `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Automatic Python installation failed (winget exit code $LASTEXITCODE)." -ForegroundColor Red
        Write-Host "No Petasos project files were removed. Use the manual guide below."
        return $false
    }

    $installedPython = Find-SafeBasePython
    if ($null -eq $installedPython) {
        Write-Host "Python installation finished, but the executable was not found yet." -ForegroundColor Yellow
        Write-Host "Close this window and run setup_petasos.cmd again."
        return $false
    }

    Write-Check "Python 3.12 automatic installation" $true "$($installedPython.Path) - $($installedPython.Version)"
    return $true
}

function Start-RosGuidedSetup {
    $installer = Join-Path $PSScriptRoot "install_ros2_humble.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "The guided ROS installer is missing: $installer"
    }

    Write-Host ""
    Write-Host "RViz and MoveIt require WSL 2, Ubuntu 22.04, and ROS 2 Humble."
    Write-Host "The guided installer explains each system change before it runs."
    $answer = Read-Host "Start the guided RViz and MoveIt setup now? (Y/N)"
    if ($answer -match "^[Yy]$") {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer 2>&1 | Out-Host
        $guidedSetupExitCode = [int]$LASTEXITCODE
        return $guidedSetupExitCode
    }
    Write-Host "Skipped the optional RViz and MoveIt setup."
    return 2
}

Write-Host "Diagnostic location: $ProjectRoot"
Write-Host ""

$basePython = Find-SafeBasePython
Write-Check `
    "Compatible Python" `
    ($null -ne $basePython) `
    $(if ($null -ne $basePython) {
        "$($basePython.Path) - $($basePython.Version)"
    } else {
        "Python 3.10 through 3.13 is required. It will not be installed system-wide."
    })

$pythonState = Test-PetasosPython $VenvPython
Write-Check "Petasos project-local .venv" $pythonState.Ready $pythonState.Detail

$inventorReady = Test-Inventor
Write-Check `
    "Autodesk Inventor integration" `
    $inventorReady `
    $(if ($inventorReady) {
        "Direct Inventor connection is available."
    } else {
        "Optional. It is not required for STEP or STL import."
    })

$wslState = Test-WslRos
Write-Check "WSL - ROS 2 complete toolchain" $wslState.Ros $wslState.Detail

$pythonInstalledNow = $false
if ($null -eq $basePython -and -not $CheckOnly) {
    $pythonInstalledNow = Install-CompatiblePythonWithWinget
    if ($pythonInstalledNow) {
        $basePython = Find-SafeBasePython
    }
}

if ($null -eq $basePython) {
    Show-PythonInstallGuide
} elseif (-not $CheckOnly -and -not $pythonState.Ready) {
    Write-Host ""
    Write-Host "Only this path will be modified: $ProjectRoot\.venv"
    $createEnvironment = $pythonInstalledNow
    if (-not $createEnvironment) {
        $answer = Read-Host "Create or repair the project-local Python environment? (Y/N)"
        $createEnvironment = ($answer -match "^[Yy]$")
    } else {
        Write-Host "Continuing with the project-local Petasos environment setup."
    }
    if ($createEnvironment) {
        Install-LocalEnvironment $basePython
        $pythonState = Test-PetasosPython $VenvPython
        Write-Check "Petasos project-local .venv recheck" $pythonState.Ready $pythonState.Detail
    } else {
        Write-Host "Skipped Python environment installation."
    }
}

$rosSetupExitCode = 0
if ($null -ne $basePython -and -not $CheckOnly -and -not $wslState.Ros) {
    $rosSetupExitCode = Start-RosGuidedSetup
    if ($rosSetupExitCode -eq 0) {
        $wslState = Test-WslRos
    } else {
        Write-Host ""
        Write-Host "The WSL / ROS setup is not complete yet (step code $rosSetupExitCode)." -ForegroundColor Yellow
        Write-Host "Follow the message above, then run setup_petasos.cmd again."
        $koIncomplete = [Text.Encoding]::UTF8.GetString(
            [Convert]::FromBase64String("V1NMIC8gUk9TIOyEpOy5mOqwgCDslYTsp4Eg7JmE66OM65CY7KeAIOyViuyVmOyKteuLiOuLpC4=")
        )
        $koRetry = [Text.Encoding]::UTF8.GetString(
            [Convert]::FromBase64String("7JyEIOyViOuCtOulvCDrlLDrpbgg65KkIHNldHVwX3BldGFzb3MuY21k66W8IOuLpOyLnCDsi6TtlontlZjshLjsmpQu")
        )
        Write-Host "$koIncomplete (step code $rosSetupExitCode)." -ForegroundColor Yellow
        Write-Host $koRetry
    }
}

Write-Host ""
Write-Host "Safety report:"
Write-Host "  - Python 3.12 was installed only if you explicitly approved it."
Write-Host "  - WSL, Ubuntu, ROS, MoveIt, and Inventor were not installed without a separate confirmation."
Write-Host "  - Petasos does not edit PATH, the registry, or Windows features without separate approval."
Write-Host "  - The approved official Python installer may register Python for the current user."
Write-Host "  - A copied or damaged .venv is backed up before Petasos rebuilds it."
Write-Host "  - Existing environments are not removed unless you explicitly approve resetting an incomplete Ubuntu registration."

if (-not $wslState.Ros) {
    Write-Host ""
    Write-Host "For RViz or MoveIt, install Ubuntu-22.04 and ROS 2 Humble separately."
    Write-Host "WSL is not required when only using the editor and URDF export."
}

if (-not $pythonState.Ready -or -not $wslState.Ros -or $rosSetupExitCode -ne 0) {
    exit 2
}
exit 0
