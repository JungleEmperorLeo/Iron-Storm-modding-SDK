@echo off
rem Makes IronStormConsole.exe (the game with the console) in your Iron Storm folder. Game.exe itself is never changed. Needs Python 3.
rem Usage: double-click (uses the game folder above modtools), or drag your Iron Storm folder onto this file,
rem        or: make_console_exe.bat "C:\path\to\Iron Storm"
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto havepy
python -c "import sys; sys.exit(sys.version_info[0] < 3)" >nul 2>nul
if not errorlevel 1 set "PY=python"
:havepy
if defined PY goto gotpy
echo Python 3 was not found. Install it from python.org (tick "Add Python to PATH"), then run this again.
pause
exit /b 1
:gotpy
if not "%~1"=="" set "ISMOD_GAME=%~f1"
%PY% make_console_exe.py
echo.
echo Run IronStormConsole.exe to play with the console (press the ` key in game).
pause
