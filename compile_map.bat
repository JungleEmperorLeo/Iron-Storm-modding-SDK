@echo off
rem Usage: compile_map.bat "path\to\map.map" isdm5   (converts + installs, no launch)
set MAPF=%~f1
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% map2is.py "%MAPF%" --name %2 --install
exit /b %errorlevel%
