@echo off
chcp 65001 >nul 2>&1
title Meshtastic TG Relay
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo.
echo  ================================================================
echo     MESHTASTIC ^<--^> TELEGRAM   public relay
echo  ================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto no_python

if not exist "relay.py" goto no_relay
echo  [OK]  relay.py

findstr /c:"PASTE_RELAY_BOT_TOKEN_HERE" relay.py >nul
if not errorlevel 1 goto no_token
echo  [OK]  Token is set

python -c "import meshtastic, telegram" >nul 2>&1
if errorlevel 1 goto install_deps
echo  [OK]  Dependencies ready
goto pick_port

:install_deps
echo  [..]  Installing dependencies from ..\requirements.txt ...
python -m pip install -r ..\requirements.txt
if errorlevel 1 goto install_failed
echo  [OK]  Dependencies installed

:pick_port
echo.
echo  Available COM ports:
python -c "import serial.tools.list_ports as lp; ps=list(lp.comports()); print('\n'.join('   '+p.device.ljust(8)+'  '+(p.description or '') for p in ps) if ps else '   (none found - check USB cable)')"
echo.
echo   Enter: COM number (e.g. 3), full name (COM3), 'a' = auto, 'q' = quit
set "port="
set /p "port=   Your choice: "

if /i "%port%"=="q" exit /b 0
if /i "%port%"=="a" set "port="
if "%port%"=="" goto run_auto

REM strip optional COM prefix, then always prepend COM
set "p=%port%"
if /i "%p:~0,3%"=="COM" set "p=%p:~3%"
set "PORT_ARG=--port COM%p%"
goto run

:run_auto
set "PORT_ARG="

:run
echo.
echo  ================================================================
echo   Starting relay.py %PORT_ARG%
echo   Press Ctrl+C to stop
echo  ================================================================
echo.
python relay.py %PORT_ARG%
echo.
echo  ================================================================
echo   Relay exited with code %errorlevel%.
echo  ================================================================
pause
exit /b 0

:no_python
echo  [X]  Python not found in PATH.
echo       Install Python 3.10+ from python.org
echo       and enable "Add Python to PATH" during install.
pause
exit /b 1

:no_relay
echo  [X]  relay.py not found next to this batch file.
pause
exit /b 1

:no_token
echo  [!]  TOKEN NOT SET
echo       Open relay.py, find PASTE_RELAY_BOT_TOKEN_HERE
echo       and replace it with your @BotFather token.
pause
exit /b 1

:install_failed
echo  [X]  pip install failed. Fix network/permissions and retry.
pause
exit /b 1
