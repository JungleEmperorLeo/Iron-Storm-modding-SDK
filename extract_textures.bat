@echo off
rem Exports the game's stock textures as PNGs for TrenchBroom (once per computer). Needs Python 3.
rem Usage: double-click (uses the game folder above modtools), or drag your Iron Storm game folder onto this file,
rem        or: extract_textures.bat "C:\path\to\Iron Storm"
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
set "GAME=%~dp0.."
if not "%~1"=="" set "GAME=%~f1"
if exist "%GAME%\Models.ibf" goto found
echo Models.ibf was not found in:
echo   %GAME%
echo Put the modtools folder inside your Iron Storm folder, or drag the Iron Storm folder onto this file.
pause
exit /b 1
:found
%PY% -c "import PIL" >nul 2>nul
if errorlevel 1 %PY% -m pip install --quiet pillow
echo Exporting textures from:
echo   %GAME%
%PY% extract_textures.py "%GAME%"
echo.
echo Done. Restart TrenchBroom to see the textures (modtools\trenchbroom\textures).
pause
