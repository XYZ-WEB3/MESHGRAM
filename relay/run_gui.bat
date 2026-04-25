@echo off
chcp 65001 >nul 2>&1
title Meshtastic TG Relay - GUI
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

python --version >nul 2>&1
if errorlevel 1 goto no_python

python -c "import PyQt6, meshtastic, telegram, serial" >nul 2>&1
if errorlevel 1 goto install_deps

goto launch

:install_deps
echo [..] Installing dependencies from ..\requirements.txt ...
python -m pip install -r ..\requirements.txt
if errorlevel 1 goto install_failed

:launch
start "" pythonw gui.py
exit /b 0

:no_python
echo [X] Python not found in PATH.
pause
exit /b 1

:install_failed
echo [X] pip install failed.
pause
exit /b 1
