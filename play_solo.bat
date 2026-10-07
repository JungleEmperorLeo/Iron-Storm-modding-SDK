@echo off
rem Plays what is installed in the campaign Test slot. Game.exe is never changed: a patched copy (ISModGame.exe)
rem is made for this run and deleted when the game closes.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw launcher.py --test & exit /b 0)
where python >nul 2>nul && (start "" python launcher.py --test & exit /b 0)
start "" py launcher.py --test
