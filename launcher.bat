@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw launcher.py) || (where python >nul 2>nul && (python launcher.py) || (py launcher.py))
