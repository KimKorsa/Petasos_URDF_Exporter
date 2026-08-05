@echo off
rem Keep this launcher ASCII-only. Korean guidance is emitted by PowerShell.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Petasos Safe Setup

echo.
echo Petasos Safe Setup
echo ----------------------------------------
echo This helper does not change Windows without your confirmation.
echo If approved, Python 3.12 is installed for the current Windows user.
echo Petasos Python packages are installed only into this project's .venv.
echo.

if not exist "%~dp0tools\setup_petasos.ps1" (
    echo [ERROR] The setup helper file is missing.
    echo.
    echo Do not run setup_petasos.cmd inside a ZIP preview window.
    echo 1. Close this window.
    echo 2. Right-click the downloaded ZIP and choose "Extract All".
    echo 3. Open the extracted fusion2urdf-master folder.
    echo 4. Run setup_petasos.cmd again there.
    echo.
    echo Current location: %~dp0
    pause
    exit /b 2
)

if not exist "%~dp0tools\install_ros2_humble.ps1" (
    echo [ERROR] The guided WSL and ROS setup file is missing.
    echo Copy the complete tools folder together with setup_petasos.cmd.
    echo.
    pause
    exit /b 2
)

findstr /c:"PETASOS_SETUP_VERSION=2026.08.03.20" "%~dp0tools\setup_petasos.ps1" >nul
if errorlevel 1 goto :version_mismatch
findstr /c:"PETASOS_ROS_SETUP_VERSION=2026.08.03.20" "%~dp0tools\install_ros2_humble.ps1" >nul
if errorlevel 1 goto :version_mismatch

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_petasos.ps1"
set "PETASOS_SETUP_EXIT=%ERRORLEVEL%"

echo.
if not "%PETASOS_SETUP_EXIT%"=="0" (
    echo Setup is incomplete. Review the guidance above.
) else (
    echo Setup check completed successfully.
)
pause
exit /b %PETASOS_SETUP_EXIT%

:version_mismatch
echo [ERROR] Petasos setup files are from different versions.
echo setup_petasos.cmd alone is not the installer logic.
echo Copy setup_petasos.cmd and the complete tools folder from the same Petasos version.
echo.
pause
exit /b 2
