@echo off
rem Usage: build_mod.bat "path\to\any map in the mod folder"   (builds every map listed in that folder's mod.json)
set MODDIR=%~dp1.
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% build_mod.py "%MODDIR%"
exit /b %errorlevel%
