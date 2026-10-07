@echo off
rem Builds GexPad.exe (the level script editor) into this folder, with the game's icon (needs Python; installs PyInstaller the first time).
cd /d "%~dp0"
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -m pip install --quiet pyinstaller
%PY% -m PyInstaller --noconfirm --onefile --windowed --name GexPad --icon "%~dp0launcher.ico" ^
  --add-data "%~dp0launcher.ico;." --distpath . --workpath build\pyinstaller --specpath build\pyinstaller --paths "%~dp0." "%~dp0gexpad.py"
if exist GexPad.exe (echo. & echo Built: %~dp0GexPad.exe) else (echo Build failed)
pause
