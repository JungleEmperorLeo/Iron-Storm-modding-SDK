@echo off
rem Builds ISModLauncher.exe into the Iron Storm folder (needs Python; installs PyInstaller the first time).
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -m pip install --quiet pyinstaller pillow
%PY% -m PyInstaller --noconfirm --onefile --windowed --name ISModLauncher --icon "%~dp0launcher.ico" ^
  --add-data "%~dp0launcher.ico;." --add-data "%~dp0sdk\bin\ISModLoader.dll;." --add-data "%~dp0sdk\bin\ISModLoader_core.dll;." --hidden-import ismap.modpack --hidden-import ismap.bigfile --hidden-import ismap.gamepatch ^
  --distpath .. --workpath build\pyinstaller --specpath build\pyinstaller --paths "%~dp0." "%~dp0launcher.py"
if exist ..\ISModLauncher.exe (echo. & echo Built: %~dp0..\ISModLauncher.exe) else (echo Build failed)
pause
