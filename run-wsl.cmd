@echo off
setlocal EnableDelayedExpansion

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL is not installed or wsl.exe is not on PATH. 1>&2
  exit /b 1
)

set "PROJECT_DIR=%~dp0"
if "!PROJECT_DIR:~0,2!"=="\\" (
  for /f "tokens=1,2,* delims=\" %%A in ("!PROJECT_DIR!") do (
    set "PATH_DISTRO=%%B"
    set "WSL_PROJECT=/%%C"
  )
  set "WSL_PROJECT=!WSL_PROJECT:\=/!"
  if not defined NI_MODEL_WSL_DISTRO set "NI_MODEL_WSL_DISTRO=!PATH_DISTRO!"
) else (
  for /f "usebackq delims=" %%I in (`wsl.exe wslpath -u "!PROJECT_DIR!"`) do set "WSL_PROJECT=%%I"
)

if not defined WSL_PROJECT (
  echo Could not translate the repository path into WSL. 1>&2
  exit /b 1
)

if defined NI_MODEL_DEBUG echo WSL distribution=!NI_MODEL_WSL_DISTRO! project=!WSL_PROJECT!

if defined NI_MODEL_WSL_DISTRO (
  wsl.exe --distribution "!NI_MODEL_WSL_DISTRO!" --cd "!WSL_PROJECT!" ./run.sh %*
) else (
  wsl.exe --cd "!WSL_PROJECT!" ./run.sh %*
)

exit /b %errorlevel%
