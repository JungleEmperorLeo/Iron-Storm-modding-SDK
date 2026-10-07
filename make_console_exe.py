"""Makes a permanent patched copy of the game with the console: IronStormConsole.exe + ISModLoader.dll in the Iron Storm folder.
Game.exe itself is never changed. Run IronStormConsole.exe to play with the console (press ` in game)."""
import os, shutil, sys
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
from ismap import gamepatch
game = os.environ.get('ISMOD_GAME') or os.path.dirname(here)
d = open(os.path.join(game, 'Game.exe'), 'rb').read()
if not gamepatch.is_stock(d):
    o = os.path.join(game, 'Game.exe.orig'); d = open(o, 'rb').read() if os.path.exists(o) else b''
    if not gamepatch.is_stock(d): sys.exit('Game.exe is not the stock v1.041')
open(os.path.join(game, 'IronStormConsole.exe'), 'wb').write(gamepatch.patch(d))
shutil.copyfile(os.path.join(here, 'sdk', 'bin', 'ISModLoader.dll'), os.path.join(game, 'ISModLoader.dll'))
core = os.path.join(here, 'sdk', 'bin', 'ISModLoader_core.dll')
if os.path.exists(core): shutil.copyfile(core, os.path.join(game, 'ISModLoader_core.dll'))
print('Made IronStormConsole.exe and ISModLoader.dll in', game)
