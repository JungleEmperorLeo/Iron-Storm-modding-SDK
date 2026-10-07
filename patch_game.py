#!/usr/bin/env python3
"""Patch Game.exe (v1.041) for single-player custom levels.  The original is kept as Game.exe.orig.

  python patch_game.py [GAME_DIR]                 patch (default: New Game -> difficulty -> loads the campaign Test slot)
  python patch_game.py [GAME_DIR] --levelselect   New Game opens the level-select page (Level 1-6 + Test) instead
  python patch_game.py [GAME_DIR] --undo          restore the original Game.exe

Both modes also add the autostart hook: if a file named solo.flag exists in the game folder when the main menu
opens, the game deletes it and loads the Test slot immediately (play_solo.bat creates it; Trenchbroom's
Launch Engine uses that).  Without solo.flag the game behaves normally."""
import os, sys, shutil, struct
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
game = args[0] if args else os.path.dirname(HERE)
exe = os.path.join(game, 'Game.exe'); orig = exe + '.orig'
PAGE, LEVEL = 0x74224, 0x7422d     # operand of 'push <page>' and of 'mov byte [esi+709h], <level>' in the New Game handler
HOOK, CAVE = 0x71fa0, 0x131da0     # SetPage() entry, and an unused zero-filled gap at the end of .text
if '--undo' in sys.argv:
    if not os.path.exists(orig): sys.exit('no %s to restore' % orig)
    shutil.copyfile(orig, exe); print('restored the original Game.exe'); sys.exit(0)
mode = 'levelselect' if '--levelselect' in sys.argv else 'direct'
src = orig if os.path.exists(orig) else exe       # always patch from the pristine file
d = bytearray(open(src, 'rb').read())
if d[PAGE - 1] != 0x6a or d[PAGE + 1:PAGE + 3] != b'\x8b\xce' or d[PAGE] not in (0x0a, 0x0b) or d[LEVEL] not in (0, 1) \
        or d[HOOK:HOOK + 6] != bytes.fromhex('558bec83e4f8') or any(d[CAVE:CAVE + 0x80]):
    sys.exit('unexpected bytes at the patch sites: this is not the (stock) Game.exe v1.041 the patch was made for')
if not os.path.exists(orig): shutil.copyfile(exe, orig); print('saved', orig)
d[PAGE] = 0x0b if mode == 'levelselect' else 0x0a
d[LEVEL] = 1 if mode == 'levelselect' else 0
CODE = bytes.fromhex('837c2404007534515268001e5300ff158420530083f8ff5a5974205168001e5300ff156420530059c68109070000006a016a00e84817f4ffc204005589e583e4f8e9c001f4ff')
d[CAVE:CAVE + len(CODE)] = CODE
d[CAVE + 0x60:CAVE + 0x6a] = b'solo.flag\0'
rel = (0x400000 + CAVE) - (0x400000 + HOOK + 5)
d[HOOK:HOOK + 6] = b'\xe9' + struct.pack('<i', rel) + b'\x90'
open(exe, 'wb').write(d); print('patched', exe, '(%s + autostart hook)' % mode)
