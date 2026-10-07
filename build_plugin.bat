@echo off
rem Usage: build_plugin.bat FOLDER   (compiles the .c/.cpp files in FOLDER into FOLDER\<folder name>.dll)
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -m ismap.plugins "%~f1"
pause
