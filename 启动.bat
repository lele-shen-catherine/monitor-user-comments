@echo off
setlocal
cd /d "%~dp0"
set "UV_CACHE_DIR=%~dp0.runtime\uv-cache"
where uv >nul 2>nul
if errorlevel 1 (
  echo 正在安装 Python 管理工具 uv...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:TEMP 'uv-install.ps1'; Invoke-WebRequest https://astral.sh/uv/install.ps1 -OutFile $p; & $p; Remove-Item $p"
  set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
)
uv run --python 3.11 --with certifi python scripts\setup_and_start.py
if errorlevel 1 pause
endlocal
