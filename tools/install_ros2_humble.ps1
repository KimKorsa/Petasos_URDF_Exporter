# PETASOS_ROS_SETUP_VERSION=2026.08.03.20
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

$rosSetupMutex = [System.Threading.Mutex]::new(
    $false,
    "Local\PetasosA2RosSetup"
)
try {
    $rosSetupLockAcquired = $rosSetupMutex.WaitOne(0, $false)
}
catch [System.Threading.AbandonedMutexException] {
    $rosSetupLockAcquired = $true
}
if (-not $rosSetupLockAcquired) {
    Write-Host "Another Petasos WSL/ROS setup is already running." -ForegroundColor Yellow
    Write-Host "Keep the existing setup window open and close this duplicate window."
    exit 4
}

function Get-Utf8Text {
    param([string]$Base64)
    return [Text.Encoding]::UTF8.GetString(
        [Convert]::FromBase64String($Base64)
    )
}

$Distro = "Ubuntu-22.04"
$LinuxInstaller = Join-Path $PSScriptRoot "install_ros2_humble.sh"
$DiagnosticLogPath = Join-Path $env:TEMP (
    "petasos-ros-check-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss")
)
"Petasos ROS check $(Get-Date -Format o)" |
    Out-File -LiteralPath $DiagnosticLogPath -Encoding utf8

function ConvertFrom-NativeText {
    param([object]$Value)
    if ($null -eq $Value) {
        return ""
    }
    $text = (($Value | ForEach-Object { [string]$_ }) -join "`n")
    return ($text -replace "`0", "").TrimStart([char]0xFEFF).Trim()
}

function Invoke-WslCapture {
    param([string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & wsl.exe @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    $text = ConvertFrom-NativeText $output
    "`n[command] wsl.exe $($Arguments -join ' ')`n[exit] $exitCode`n[output]`n$text" |
        Out-File -LiteralPath $DiagnosticLogPath -Append -Encoding utf8
    return [pscustomobject]@{
        ExitCode = [int]$exitCode
        Text = $text
        Lines = @($output)
    }
}

function Get-RegisteredWslDistros {
    try {
        $capture = Invoke-WslCapture @("--list", "--quiet")
        if ($capture.ExitCode -ne 0) {
            return @()
        }
        $names = @()
        foreach ($line in $capture.Lines) {
            $name = ConvertFrom-NativeText $line
            if ($name) {
                $names += $name
            }
        }
        return @($names)
    }
    catch {
        return @()
    }
}

function Get-UbuntuRelease {
    $releaseCommand = '. /etc/os-release && printf "%s|%s" "$ID" "$VERSION_ID"'
    $capture = Invoke-WslCapture @("-d", $Distro, "--", "bash", "-lc", $releaseCommand)
    $release = $capture.Text
    if ($capture.ExitCode -eq 0 -and $release) {
        return $release
    }

    # Fallback avoids shell-variable quoting entirely and parses os-release on
    # Windows if an unusual WSL/PowerShell combination returned no text.
    $fallback = Invoke-WslCapture @("-d", $Distro, "--", "cat", "/etc/os-release")
    if ($fallback.ExitCode -ne 0) {
        return ""
    }
    $rawText = $fallback.Text
    $idMatch = [regex]::Match($rawText, '(?m)^ID="?([^"\r\n]+)"?\s*$')
    $versionMatch = [regex]::Match($rawText, '(?m)^VERSION_ID="?([^"\r\n]+)"?\s*$')
    if (-not $idMatch.Success -or -not $versionMatch.Success) {
        return ""
    }
    return "$($idMatch.Groups[1].Value)|$($versionMatch.Groups[1].Value)"
}

function Test-UbuntuDistro {
    try {
        $capture = Invoke-WslCapture @(
            "-d", $Distro, "--", "bash", "-lc", "test -f /etc/os-release"
        )
        return ($capture.ExitCode -eq 0)
    }
    catch {
        return $false
    }
}

function Test-UbuntuRegistered {
    return ((Get-RegisteredWslDistros) -contains $Distro)
}

function Test-HumbleReady {
    try {
        $command = (
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
        )
        $capture = Invoke-WslCapture @("-d", $Distro, "--", "bash", "-lc", $command)
        return ($capture.ExitCode -eq 0)
    }
    catch {
        return $false
    }
}

function Invoke-ElevatedWslBootstrap {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logPath = Join-Path $env:TEMP "petasos-wsl-bootstrap-$stamp.log"
    $escapedLogPath = $logPath.Replace("'", "''")

    # Start-Process cannot combine -Verb RunAs with output redirection. The
    # elevated script therefore records the real Windows/WSL output itself.
    $adminScript = @'
$ErrorActionPreference = "Stop"
$logPath = '__PETASOS_LOG_PATH__'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:WSL_UTF8 = "1"

function Write-SetupLog([string]$Message) {
    $Message | Out-File -LiteralPath $logPath -Append -Encoding utf8
    Write-Host $Message
}

function Invoke-LoggedWsl([string[]]$Arguments, [string]$Label) {
    Write-SetupLog ""
    Write-SetupLog "[$Label] wsl.exe $($Arguments -join ' ')"
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe @Arguments 2>&1 | ForEach-Object {
        $line = [string]$_
        $line | Out-File -LiteralPath $logPath -Append -Encoding utf8
        Write-Host $line
    }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    Write-SetupLog "[$Label] exit code: $exitCode"
    return [int]$exitCode
}

try {
    "Petasos WSL bootstrap $(Get-Date -Format o)" |
        Out-File -LiteralPath $logPath -Encoding utf8

    $restartRequired = $false
    foreach ($featureName in @(
        "Microsoft-Windows-Subsystem-Linux",
        "VirtualMachinePlatform"
    )) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName
        Write-SetupLog "[Windows feature] $featureName = $($feature.State)"
        if ($feature.State -ne "Enabled") {
            Write-SetupLog "[Windows feature] Enabling $featureName (no automatic restart)..."
            $result = Enable-WindowsOptionalFeature `
                -Online `
                -FeatureName $featureName `
                -All `
                -NoRestart
            Write-SetupLog "[Windows feature] $featureName result = $($result.State); restart = $($result.RestartNeeded)"
            if ($result.RestartNeeded -eq $true -or $result.RestartNeeded -eq "Yes") {
                $restartRequired = $true
            }
        }
    }

    $processor = Get-CimInstance Win32_Processor | Select-Object -First 1
    $computer = Get-CimInstance Win32_ComputerSystem
    Write-SetupLog "[Virtualization] Firmware enabled = $($processor.VirtualizationFirmwareEnabled)"
    Write-SetupLog "[Virtualization] SLAT supported = $($processor.SecondLevelAddressTranslationExtensions)"
    Write-SetupLog "[Virtualization] Hypervisor present = $($computer.HypervisorPresent)"
    $bcdOutput = & bcdedit.exe /enum "{current}" 2>&1 | Out-String
    $hypervisorLaunchOff = $bcdOutput -match "(?im)^hypervisorlaunchtype\s+Off\s*$"
    Write-SetupLog "[Virtualization] hypervisorlaunchtype Off = $hypervisorLaunchOff"

    if ($restartRequired) {
        Write-SetupLog "RESTART_REQUIRED: Windows enabled the WSL features. Restart Windows before continuing."
        exit 3
    }

    $updateCode = Invoke-LoggedWsl -Arguments @("--update") -Label "WSL update"
    if ($updateCode -ne 0) {
        Write-SetupLog "[WSL update] Update failed, but the installer will test whether the installed WSL can continue."
    }

    $defaultCode = Invoke-LoggedWsl `
        -Arguments @("--set-default-version", "2") `
        -Label "WSL 2 default"
    if ($defaultCode -ne 0) {
        Write-SetupLog "FAILED_STEP: Could not set WSL 2 as the default version."
        exit $defaultCode
    }

    $registeredOutput = & wsl.exe --list --quiet 2>&1 | Out-String
    $registeredText = $registeredOutput -replace "`0", ""
    if ($registeredText -match "(?im)^\s*Ubuntu-22\.04\s*$") {
        Write-SetupLog "[Ubuntu-22.04 install] Distribution is already registered; installation skipped."
        $installCode = 0
    }
    else {
        Write-SetupLog "[Ubuntu-22.04 install] Using direct web download instead of the Microsoft Store delivery path."
        Write-SetupLog "[Ubuntu-22.04 install] Download and registration progress will appear below when Windows reports it."
        $installCode = Invoke-LoggedWsl `
            -Arguments @("--install", "--web-download", "--no-launch", "-d", "Ubuntu-22.04") `
            -Label "Ubuntu-22.04 install"
    }
    if ($installCode -ne 0) {
        $installLog = Get-Content -LiteralPath $logPath -Raw
        if ($installLog -match "ERROR_ALREADY_EXISTS") {
            $registeredRetry = & wsl.exe --list --quiet 2>&1 | Out-String
            if (($registeredRetry -replace "`0", "") -match "(?im)^\s*Ubuntu-22\.04\s*$") {
                Write-SetupLog "[Ubuntu-22.04 install] ERROR_ALREADY_EXISTS confirmed an existing distribution; continuing."
                $installCode = 0
            }
        }
        if ($installLog -match "HCS_E_HYPERV_NOT_INSTALLED") {
            Write-SetupLog "PETASOS_CAUSE: HYPERVISOR_NOT_AVAILABLE"
        }
        if ($installCode -ne 0) {
            Write-SetupLog "FAILED_STEP: Ubuntu-22.04 installation failed."
            exit $installCode
        }
    }

    Write-SetupLog "WSL_BOOTSTRAP_COMPLETE"
    exit 0
}
catch {
    Write-SetupLog "UNHANDLED_ERROR: $($_.Exception.Message)"
    Write-SetupLog ($_ | Out-String)
    exit 1
}
'@
    $adminScript = $adminScript.Replace(
        "__PETASOS_LOG_PATH__",
        $escapedLogPath
    )
    $encodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($adminScript)
    )
    $process = Start-Process `
        -FilePath "powershell.exe" `
        -Verb RunAs `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", $encodedCommand
        ) `
        -PassThru

    $waitedSeconds = 0
    while (-not $process.WaitForExit(5000)) {
        $waitedSeconds += 5
        if (($waitedSeconds % 15) -eq 0) {
            $lastPhase = ""
            if (Test-Path -LiteralPath $logPath -PathType Leaf) {
                $lastPhase = Get-Content -LiteralPath $logPath -Tail 1
            }
            Write-Host (
                "[WSL setup] Still working... elapsed {0} seconds" -f
                $waitedSeconds
            ) -ForegroundColor Cyan
            if ($lastPhase) {
                Write-Host "  Latest: $lastPhase"
            }
        }
    }
    $process.Refresh()

    Write-Host ""
    $logText = ""
    if (Test-Path -LiteralPath $logPath -PathType Leaf) {
        $logText = Get-Content -LiteralPath $logPath -Raw
        Write-Host "Windows WSL setup details:" -ForegroundColor Cyan
        Get-Content -LiteralPath $logPath -Tail 80 | Out-Host
        Write-Host ""
        Write-Host "Full diagnostic log: $logPath"
    }
    else {
        Write-Host "The administrator process did not create its diagnostic log." -ForegroundColor Red
        Write-Host "Administrator approval may have been cancelled."
    }

    if ($logText -match "PETASOS_CAUSE: HYPERVISOR_NOT_AVAILABLE") {
        Write-Host ""
        Write-Host "Detected cause: the Windows hypervisor is not running." -ForegroundColor Yellow
        if ($logText -match "Firmware enabled = False") {
            Write-Host "Hardware virtualization is disabled in BIOS/UEFI."
            Write-Host "Enable Intel Virtualization Technology (VT-x) or AMD SVM/AMD-V,"
            Write-Host "save the firmware settings, and restart Windows."
        }
        elseif ($logText -match "hypervisorlaunchtype Off = True") {
            Write-Host "Windows is configured not to start its hypervisor."
            Write-Host "In Administrator PowerShell run:"
            Write-Host "  bcdedit /set hypervisorlaunchtype auto"
            Write-Host "Then restart Windows and run setup_petasos.cmd again."
        }
        else {
            Write-Host "Confirm virtualization is Enabled in Task Manager > Performance > CPU."
            Write-Host "If it is Disabled, enable Intel VT-x or AMD SVM/AMD-V in BIOS/UEFI."
            Write-Host "Then restart Windows and run setup_petasos.cmd again."
        }
    }

    return [pscustomobject]@{
        ExitCode = [int]$process.ExitCode
        LogPath = $logPath
    }
}

Write-Host ""
Write-Host "Petasos guided WSL / ROS 2 setup"
Write-Host "================================"
Write-Host "Nothing is installed until you answer Y at the relevant step."
Write-Host (Get-Utf8Text "UGV0YXNvcyBXU0wgLyBST1MgMiDshKTsuZgg64+E7Jqw66+4")
Write-Host (Get-Utf8Text "6rCBIOuLqOqzhOyXkOyEnCBZ66W8IOyeheugpe2VmOq4sCDsoITsl5DripQg7JWE66y06rKD64+EIOyEpOy5mO2VmOyngCDslYrsirXri4jri6Qu")
Write-Host ""

if ($CheckOnly) {
    if (-not (Test-UbuntuDistro)) {
        Write-Host "CHECK_ONLY: Ubuntu-22.04 is not ready. No changes made."
        exit 2
    }
    if (-not (Test-HumbleReady)) {
        Write-Host "CHECK_ONLY: ROS 2 Humble, RViz, or MoveIt is incomplete. No changes made."
        exit 2
    }
    Write-Host "CHECK_ONLY: ROS 2 Humble, RViz, and MoveIt are ready. No changes made."
    exit 0
}

if (-not (Test-UbuntuDistro) -and (Test-UbuntuRegistered)) {
    Write-Host "Ubuntu-22.04 is installed, but its first-run setup is incomplete." -ForegroundColor Yellow
    Write-Host "Ubuntu will open in a separate window. Create its Linux username and password."
    Write-Host "When the Linux prompt appears, type exit and return to this window."
    $answer = Read-Host "Continue Ubuntu first-run setup? (Y/N)"
    if ($answer -notmatch "^[Yy]$") {
        Write-Host "Ubuntu first-run setup skipped."
        exit 2
    }

    # Clear a stale WSL VM/service state before treating the registration as
    # damaged. This is non-destructive and often repairs a first-run timeout.
    $null = Invoke-WslCapture @("--shutdown")
    $firstRun = Start-Process `
        -FilePath "wsl.exe" `
        -ArgumentList @("-d", $Distro) `
        -Wait `
        -PassThru

    if ($firstRun.ExitCode -ne 0 -or -not (Test-UbuntuDistro)) {
        $probe = Invoke-WslCapture @(
            "-d", $Distro, "--", "bash", "-lc", "test -f /etc/os-release"
        )
        Write-Host "Ubuntu first-run setup is still incomplete." -ForegroundColor Yellow
        Write-Host "Diagnostic log: $DiagnosticLogPath"

        if ($probe.Text -match "E_UNEXPECTED|0x800705b4") {
            Write-Host ""
            Write-Host "The Ubuntu name is registered, but its virtual machine was not created correctly." -ForegroundColor Yellow
            Write-Host "Petasos can remove this incomplete Ubuntu-22.04 registration and install it again."
            Write-Host "WARNING: unregistering permanently deletes files stored inside this Ubuntu distribution." -ForegroundColor Red
            $repairAnswer = Read-Host "Reset only Ubuntu-22.04 and reinstall it? (Y/N)"
            if ($repairAnswer -match "^[Yy]$") {
                $unregister = Invoke-WslCapture @("--unregister", $Distro)
                if ($unregister.ExitCode -ne 0) {
                    Write-Host "Could not remove the incomplete Ubuntu registration." -ForegroundColor Red
                    Write-Host "Diagnostic log: $DiagnosticLogPath"
                    exit 1
                }
                Write-Host "The incomplete Ubuntu-22.04 registration was removed. Reinstalling now."
            }
            else {
                Write-Host "Ubuntu reset was cancelled. No distribution data was removed."
                exit 3
            }
        }
        else {
            Write-Host "Open Ubuntu 22.04 from the Start menu, finish username/password setup,"
            Write-Host "then run setup_petasos.cmd again."
            exit 3
        }
    }
}

if (-not (Test-UbuntuDistro)) {
    Write-Host "Ubuntu-22.04 is not ready."
    Write-Host (Get-Utf8Text "VWJ1bnR1LTIyLjA06rCAIOyVhOyngSDspIDruYTrkJjsp4Ag7JWK7JWY7Iq164uI64ukLg==") -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The next step will:"
    Write-Host "  - request Windows administrator approval"
    Write-Host "  - enable WSL and Virtual Machine Platform if needed"
    Write-Host "  - download and install a separate Ubuntu-22.04 distribution"
    Write-Host "  - possibly require a Windows restart"
    Write-Host "  - possibly open Ubuntu so you can create its Linux username and password"
    Write-Host ""
    Write-Host "It will not remove or replace another WSL distribution."
    Write-Host (Get-Utf8Text "64uk66W4IFdTTCDrsLDtj6ztjJDsnYQg7IKt7KCc7ZWY6rGw64KYIOq1kOyytO2VmOyngCDslYrsirXri4jri6Qu")
    $answer = Read-Host (Get-Utf8Text "SW5zdGFsbCBXU0wgMiBhbmQgVWJ1bnR1LTIyLjA0PyAvIFdTTCAy7JmAIFVidW50dS0yMi4wNOulvCDshKTsuZjtlaDquYzsmpQ/IChZL04p")
    if ($answer -notmatch "^[Yy]$") {
        Write-Host "WSL installation skipped."
        exit 2
    }

    $bootstrap = Invoke-ElevatedWslBootstrap
    if ($bootstrap.ExitCode -eq 3) {
        Write-Host ""
        Write-Host "Windows restart is required before Ubuntu can be installed." -ForegroundColor Yellow
        Write-Host "Restart Windows, then run setup_petasos.cmd again."
        Write-Host (Get-Utf8Text "VWJ1bnR166W8IOyEpOy5mO2VmOq4sCDsoITsl5AgV2luZG93cyDsnqzrtoDtjIXsnbQg7ZWE7JqU7ZWp64uI64ukLg==") -ForegroundColor Yellow
        Write-Host (Get-Utf8Text "V2luZG93c+ulvCDsnqzrtoDtjIXtlZwg65KkIHNldHVwX3BldGFzb3MuY21k66W8IOuLpOyLnCDsi6TtlontlZjshLjsmpQu")
        exit 3
    }
    if ($bootstrap.ExitCode -ne 0) {
        Write-Host ""
        Write-Host "The Windows WSL setup failed with code $($bootstrap.ExitCode)." -ForegroundColor Red
        Write-Host "The exact failed command and Windows message are shown above."
        Write-Host "Diagnostic log: $($bootstrap.LogPath)"
        exit 1
    }

    Write-Host ""
    Write-Host "Ubuntu-22.04 download and registration completed." -ForegroundColor Green
    Write-Host "Ubuntu will now open in a separate window for its one-time user setup."
    Write-Host "Create the Linux username and password. When the Linux prompt appears, type exit."
    Write-Host (Get-Utf8Text "VWJ1bnR1LTIyLjA0IOuLpOyatOuhnOuTnOyZgCDrk7HroZ3snbQg7JmE66OM65CY7JeI7Iq164uI64ukLg==") -ForegroundColor Green
    Write-Host (Get-Utf8Text "67OE64+EIFVidW50dSDssL3sl5DshJwg7IKs7Jqp7J6Q66qF6rO8IOu5hOuwgOuyiO2YuOulvCDrp4zrk5zshLjsmpQuIExpbnV4IO2UhOuhrO2UhO2KuOqwgCDrs7TsnbTrqbQgZXhpdOulvCDsnoXroKXtlZjshLjsmpQu")

    $firstRun = Start-Process `
        -FilePath "wsl.exe" `
        -ArgumentList @("-d", $Distro) `
        -Wait `
        -PassThru

    if ($firstRun.ExitCode -ne 0 -or -not (Test-UbuntuDistro)) {
        Write-Host ""
        Write-Host "Ubuntu first-run setup is still incomplete." -ForegroundColor Yellow
        Write-Host "Open Ubuntu 22.04 from the Start menu, finish username/password setup,"
        Write-Host "then run setup_petasos.cmd again."
        Write-Host (Get-Utf8Text "VWJ1bnR1IOy1nOy0iCDshKTsoJXsnbQg7JWE7KeBIOyZhOujjOuQmOyngCDslYrslZjsirXri4jri6Qu") -ForegroundColor Yellow
        exit 3
    }

    Write-Host ""
    Write-Host "Ubuntu first-run setup completed. Continuing with ROS 2 installation." -ForegroundColor Green
    Write-Host (Get-Utf8Text "VWJ1bnR1IOy1nOy0iCDshKTsoJXsnbQg7JmE66OM65CY7JeI7Iq164uI64ukLiBST1MgMiDshKTsuZjrpbwg6rOE7IaN7ZWp64uI64ukLg==") -ForegroundColor Green
}

if (Test-HumbleReady) {
    Write-Host "ROS 2 Humble, RViz, and MoveIt are already ready. No changes made."
    exit 0
}

if (-not (Test-Path -LiteralPath $LinuxInstaller -PathType Leaf)) {
    throw "The Ubuntu installer script is missing: $LinuxInstaller"
}

$release = Get-UbuntuRelease
if ($release -ne "ubuntu|22.04") {
    Write-Host "Diagnostic log: $DiagnosticLogPath" -ForegroundColor Yellow
    throw (
        "Petasos only installs ROS 2 Humble into Ubuntu 22.04. " +
        "Detected: '$release'"
    )
}

Write-Host "Ubuntu-22.04 is ready, but the ROS environment is incomplete."
Write-Host ""
Write-Host "The next step runs only inside the Ubuntu-22.04 distribution and will:"
Write-Host "  - update Ubuntu package indexes and installed Ubuntu packages"
Write-Host "  - add the official ROS 2 apt source"
Write-Host "  - install ROS 2 Humble Desktop, RViz, MoveIt 2, ros2_control,"
Write-Host "    Gazebo ROS packages, rosdep, and colcon tools"
Write-Host "  - run the approved package-install step as root only inside Ubuntu-22.04"
Write-Host ""
Write-Host "It will not modify another WSL distribution or Windows PATH."
$answer = Read-Host "Continue with the Ubuntu ROS installation? (Y/N)"
if ($answer -notmatch "^[Yy]$") {
    Write-Host "ROS installation skipped."
    exit 2
}

$linuxPath = "/tmp/petasos-install-ros2-humble.sh"
$installerBytes = [System.IO.File]::ReadAllBytes($LinuxInstaller)
$installerBase64 = [System.Convert]::ToBase64String($installerBytes)
$stageCommand = (
    "umask 077; printf '%s' '" + $installerBase64 +
    "' | base64 -d > '" + $linuxPath + "'; chmod 700 '" + $linuxPath + "'"
)
$stageCapture = Invoke-WslCapture @(
    "-d", $Distro, "--", "bash", "-lc", $stageCommand
)
if ($stageCapture.ExitCode -ne 0) {
    Write-Host "Windows installer path: $LinuxInstaller" -ForegroundColor Yellow
    Write-Host "Diagnostic log: $DiagnosticLogPath" -ForegroundColor Yellow
    throw "Could not stage the ROS installer inside Ubuntu."
}
Write-Host "ROS installer copied safely into Ubuntu: $linuxPath"
Write-Host "Windows drive letters and non-ASCII user names are not used by this step."

$userCapture = Invoke-WslCapture @("-d", $Distro, "--", "whoami")
$linuxUser = $userCapture.Text.Trim()
if ($userCapture.ExitCode -ne 0 -or $linuxUser -notmatch '^[a-z_][a-z0-9_-]*[$]?$') {
    Write-Host "Diagnostic log: $DiagnosticLogPath" -ForegroundColor Yellow
    throw "Could not determine the default Ubuntu user."
}
Write-Host "Installing approved ROS packages as Ubuntu root; no password prompt is required."
Write-Host "The default Ubuntu user remains unchanged: $linuxUser"

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& wsl.exe -d $Distro -u root -- bash $linuxPath $linuxUser 2>&1 | ForEach-Object {
    $line = [string]$_
    $line | Out-File -LiteralPath $DiagnosticLogPath -Append -Encoding utf8
    Write-Host $line
}
$rosInstallerExitCode = $LASTEXITCODE
Invoke-WslCapture @(
    "-d", $Distro, "--", "rm", "-f", "--", $linuxPath
) | Out-Null
$ErrorActionPreference = $previousPreference
if ($rosInstallerExitCode -ne 0) {
    $diagnosticText = Get-Content -LiteralPath $DiagnosticLogPath -Raw
    if ($diagnosticText -match "nested virtualization|중첩 가상화|HCS_E_HYPERV_NOT_INSTALLED") {
        Write-Host ""
        Write-Host "ROS installation cannot run in this Windows virtual machine." -ForegroundColor Yellow
        Write-Host "The VMware host is not exposing nested virtualization required by WSL 2."
        Write-Host "This cannot be repaired by installing another Petasos package."
        Write-Host "Use one of these supported paths:"
        Write-Host "  1. Run Petasos + WSL 2 on a physical Windows computer."
        Write-Host "  2. Export the ROS workspace and run ROS 2 directly in an Ubuntu 22.04 VM."
        Write-Host "  3. Enable VMware nested virtualization if the host CPU and VMware version support it."
        Write-Host "Diagnostic log: $DiagnosticLogPath"
        exit 4
    }
    Write-Host "Diagnostic log: $DiagnosticLogPath" -ForegroundColor Yellow
    throw "The Ubuntu ROS installer exited with code $rosInstallerExitCode."
}

if (-not (Test-HumbleReady)) {
    Write-Host "Diagnostic log: $DiagnosticLogPath" -ForegroundColor Yellow
    throw "Installation finished, but the ROS 2 readiness check still failed."
}

Write-Host ""
Write-Host "ROS 2 Humble, RViz, and MoveIt are ready for Petasos."
exit 0
