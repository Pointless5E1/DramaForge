@echo off
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo [DramaForge] Missing Python virtual environment: "%ROOT%\.venv\Scripts\python.exe"
  echo Please create .venv and install backend requirements first.
  pause
  exit /b 1
)

"%ROOT%\.venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [DramaForge] The existing Python virtual environment could not be started:
  echo   "%ROOT%\.venv"
  echo Check whether its base Python is accessible before repairing the environment.
  echo Do not create a new venv on every launch.
  pause
  exit /b 1
)

if not exist "%ROOT%\frontend\node_modules" (
  echo [DramaForge] Missing frontend dependencies: "%ROOT%\frontend\node_modules"
  echo Please run npm install in "%ROOT%\frontend" first.
  pause
  exit /b 1
)

set "CLI_PROXY_ROOT=D:\CLIProxyAPI"
set "CLI_PROXY_EXE=%CLI_PROXY_ROOT%\cli-proxy-api.exe"

if not exist "%CLI_PROXY_EXE%" (
  echo [DramaForge] Missing CLI Proxy API executable: "%CLI_PROXY_EXE%"
  pause
  exit /b 1
)

start "DramaForge Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%ROOT%\backend'; & '%ROOT%\.venv\Scripts\python.exe' main.py"
if not defined DRAMAFORGE_BACKEND_DELAY set "DRAMAFORGE_BACKEND_DELAY=15"
echo [DramaForge] Waiting %DRAMAFORGE_BACKEND_DELAY% seconds for backend startup...
powershell -NoProfile -Command "Start-Sleep -Seconds %DRAMAFORGE_BACKEND_DELAY%"
start "DramaForge Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%ROOT%\frontend'; npm run dev"
start "CLI Proxy API" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%CLI_PROXY_ROOT%'; & '%CLI_PROXY_EXE%'"
