@echo off
setlocal
cd /d "%~dp0"
set "PETASOS_EXPORT_ROOT=%~dp0export"

if not exist "%~dp0tools\setup_petasos.ps1" (
    echo [ERROR] Petasos setup files are missing.
    echo Copy the complete project folder, including the tools folder.
    pause
    exit /b 2
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_petasos.ps1" -CheckOnly
if errorlevel 1 (
    echo.
    echo Petasos runtime setup is incomplete. Starting the guided installer now.
    call "%~dp0setup_petasos.cmd"
    if errorlevel 1 (
        echo.
        echo Setup is still incomplete. Follow the guidance and run start_petasos.cmd again.
        pause
        exit /b 2
    )
)

if not exist "%~dp0petasos_standalone.py" (
    echo [ERROR] Petasos files are incomplete or this CMD is running inside a ZIP preview.
    echo Right-click the downloaded ZIP, choose "Extract All", and run this file
    echo from the extracted fusion2urdf-master folder.
    echo.
    echo Current location: %~dp0
    pause
    exit /b 2
)

set "PETASOS_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "PETASOS_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PETASOS_PYTHON if exist "%USERPROFILE%\anaconda3\python.exe" set "PETASOS_PYTHON=%USERPROFILE%\anaconda3\python.exe"
if not defined PETASOS_PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PETASOS_PYTHON=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"

if not defined PETASOS_PYTHON (
    echo Python could not be found.
    echo Run setup_petasos.cmd first.
    pause
    exit /b 1
)

"%PETASOS_PYTHON%" -c "import flask, trimesh, numpy, scipy, OCP" >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo Petasos Python packages are missing or incomplete.
    echo Run setup_petasos.cmd first.
    pause
    exit /b 1
)

if exist "%~dp0tools\stop_petasos_wsl_gui.ps1" (
    echo Closing any previous Petasos RViz window.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\stop_petasos_wsl_gui.ps1"
)

echo Petasos is starting.
echo Keep this CMD window open. Closing it stops the Petasos server.
echo.
"%PETASOS_PYTHON%" "%~dp0petasos_standalone.py"
set "PETASOS_EXIT=%ERRORLEVEL%"

if "%PETASOS_EXIT%"=="3" (
    echo.
    echo Petasos is already running in another CMD window.
    echo Keep the original CMD window open, or close it before starting a new one.
    pause
    exit /b 0
)

if not "%PETASOS_EXIT%"=="0" (
    echo.
    echo Petasos stopped with an error.
    pause
    exit /b 1
)

echo.
echo Petasos server stopped.
timeout /t 2 /nobreak >nul
