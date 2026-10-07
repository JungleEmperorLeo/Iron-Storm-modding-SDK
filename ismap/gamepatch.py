"""Game.exe v1.041 patch for custom single-player levels (same bytes as patch_game.py, mode 'direct').

New Game loads the campaign Test slot, and a solo.flag file in the game folder makes the main menu start it at once.
patched_exe(game) returns (exe, temporary): Game.exe itself if it is already patched, otherwise a freshly made patched
copy ISModGame.exe next to it, which the launcher deletes when the game closes. The original Game.exe is never changed.
"""
import os, struct

PAGE, LEVEL = 0x74224, 0x7422d
HOOK, CAVE = 0x71fa0, 0x131da0
CODE = bytes.fromhex('837c2404007534515268001e5300ff158420530083f8ff5a5974205168001e5300ff156420530059c68109070000006a016a00e84817f4ffc204005589e583e4f8e9c001f4ff')
COPY = 'ISModGame.exe'

# weapon tuning (file offsets in Game.exe v1.041)
DMG_SP, DMG_MP, CLIP = 0x173870, 0x1738e8, 0x17f7c8     # bullet table: 3 floats per bullet type (speed, speed, damage); clip: int16 per weapon
SLOT, ZOOMF, ZOOM, RECOILF, RECOIL_V, RECOIL_H = 0x17f9f4, 0x17f988, 0x17f9c4, 0x17f8f4, 0x17f904, 0x17f940
SLOTS = {'knife': 0, 'sidearm': 1, 'sniper': 2, 'shotgun': 3, 'heavy': 4}   # weapon groups (read-only: moving a weapon to another group made it vanish in game; zoom/slot edits are disabled)
WEAPONS = {   # name: (bullet type or None, weapon id)
    'handgun': (2, 1), 'smg': (3, 2), 'sniper': (4, 3), 'shotgun': (5, 4), 'mg': (6, 5),
    'launcher': (None, 9), 'rocket': (None, 10), 'flamethrower': (None, 11)}

# more tuning found by reading Game.exe (offsets verified against the stock values; none of these were tested in game yet)
CLIP_T, MAXAMMO, PICKUP, RESERVE = 0x17f7c8, 0x17f7e8, 0x171f18, 0x17fa38     # clip int16 by weapon id; max reserve int16 by reserve slot; pickup amount int16 by pickup type; weapon id -> reserve slot int32
SPREAD, SPREAD_MOVE, KICK = 0x17f750, 0x17f78c, 0x17f570                       # float by weapon id; per-weapon 32-byte struct (+0x14 recoil kick, +0x18 random extra)
AI_RANGE, AI_PREFER = 0x17f804, 0x17f840                                       # float by weapon id: the farthest / preferred distance at which enemies use the weapon
PICKUP_TYPE = {'mg': 2, 'smg': 2, 'sniper': 3, 'shotgun': 4, 'handgun': 5, 'launcher': 6, 'rocket': 7, 'flamethrower': 8}
TUNABLE = ('damage', 'flash', 'clip', 'max_ammo', 'pickup', 'speed', 'spread', 'spread_move', 'recoil', 'ai_range', 'ai_preferred_range')

def weapon_stats(d):
    out = {}; rs = {v: k for k, v in SLOTS.items()}
    for n, (bt, wid) in WEAPONS.items():
        st = {'slot': rs.get(struct.unpack_from('<i', d, SLOT + 4 * wid)[0], '?'),
              'zoom': struct.unpack_from('<f', d, ZOOM + 4 * wid)[0] if d[ZOOMF + wid] else 0,
              'flash': [round(struct.unpack_from('<f', d, b + 4 * wid)[0], 3) for b in (RECOIL_V, RECOIL_H)] if d[RECOILF + wid] else 0}   # muzzle flash: [size, random extra]
        if bt is not None: st['damage'] = struct.unpack_from('<f', d, DMG_SP + 12 * bt + 8)[0]
        out[n] = st
    return out

def check_weapons(tweaks):
    """raise ValueError (with a plain message) when a mod.json weapons section has an unknown weapon or setting, or a bad value."""
    if tweaks is None: return
    if not isinstance(tweaks, dict): raise ValueError('"weapons" in mod.json must look like {"smg": {"damage": 12}}')
    for n, t in tweaks.items():
        if n not in WEAPONS: raise ValueError('unknown weapon %r in mod.json (known: %s)' % (n, ', '.join(WEAPONS)))
        if not isinstance(t, dict): raise ValueError('weapon %r in mod.json must have settings like {"damage": 12}' % n)
        for k, v in t.items():
            if k not in TUNABLE: raise ValueError('unknown weapon setting %r for %s in mod.json (known: %s)' % (k, n, ', '.join(TUNABLE)))
            ok = (isinstance(v, (int, float)) and not isinstance(v, bool)) if k not in ('flash', 'recoil') else (v == 0 or (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)))
            if not ok: raise ValueError('%s of %s in mod.json must be %s' % (k, n, 'a number' if k not in ('flash', 'recoil') else '[a, b]' + (' or 0' if k == 'flash' else '')))

def apply_weapons(d, tweaks):
    """tweaks: {"handgun": {"damage": 40, "clip": 12}, ...} -> patched bytes. Damage is per bullet (shotgun: per pellet)."""
    check_weapons(tweaks)
    d = bytearray(d)
    for n, t in (tweaks or {}).items():
        if n not in WEAPONS: raise ValueError('unknown weapon %r in mod.json (known: %s)' % (n, ', '.join(WEAPONS)))
        bt, wid = WEAPONS[n]
        if 'damage' in t:
            if bt is None: raise ValueError('damage of %s cannot be changed yet' % n)
            for base in (DMG_SP, DMG_MP): struct.pack_into('<f', d, base + 12 * bt + 8, float(t['damage']))
        for k in t:
            if k not in TUNABLE: raise ValueError('unknown weapon setting %r for %s in mod.json (known: %s)' % (k, n, ', '.join(TUNABLE)))
        if 'clip' in t: struct.pack_into('<h', d, CLIP_T + 2 * wid, int(t['clip']))               # rounds per magazine
        if 'max_ammo' in t:            # reserve ammo you can carry (smg and mg share one pool)
            struct.pack_into('<h', d, MAXAMMO + 2 * struct.unpack_from('<i', d, RESERVE + 4 * wid)[0], int(t['max_ammo']))
        if 'pickup' in t:
            if n not in PICKUP_TYPE: raise ValueError('pickup amount of %s cannot be changed' % n)
            struct.pack_into('<h', d, PICKUP + 2 * PICKUP_TYPE[n], int(t['pickup']))       # rounds in one ammo pickup
        if 'speed' in t:
            if bt is None: raise ValueError('speed of %s cannot be changed yet' % n)
            for base in (DMG_SP, DMG_MP):
                struct.pack_into('<f', d, base + 12 * bt, float(t['speed'])); struct.pack_into('<f', d, base + 12 * bt + 4, float(t['speed']))
        if 'spread' in t: struct.pack_into('<f', d, SPREAD + 4 * wid, float(t['spread']))               # aim cone when standing still
        if 'spread_move' in t: struct.pack_into('<f', d, SPREAD_MOVE + 4 * wid, float(t['spread_move']))   # extra cone per unit of movement speed
        if 'recoil' in t:              # camera kick: [base, random extra]
            r = t['recoil']; struct.pack_into('<f', d, KICK + 32 * wid + 0x14, float(r[0])); struct.pack_into('<f', d, KICK + 32 * wid + 0x18, float(r[1]))
        if 'ai_range' in t: struct.pack_into('<f', d, AI_RANGE + 4 * wid, float(t['ai_range']))
        if 'ai_preferred_range' in t: struct.pack_into('<f', d, AI_PREFER + 4 * wid, float(t['ai_preferred_range']))
        if 'flash' in t:         # muzzle flash: 0 = none, or [size, random extra size] (tested: changes the flash size)
            r = t['flash']; d[RECOILF + wid] = 1 if r else 0
            if r:
                struct.pack_into('<f', d, RECOIL_V + 4 * wid, float(r[0])); struct.pack_into('<f', d, RECOIL_H + 4 * wid, float(r[1]))
    return bytes(d)

def is_patched(d):
    return d[HOOK] == 0xe9 and d[CAVE:CAVE + len(CODE)] == CODE

def is_stock(d):
    return (len(d) > CAVE + 0x80 and d[PAGE - 1] == 0x6a and d[PAGE + 1:PAGE + 3] == b'\x8b\xce' and d[PAGE] in (0x0a, 0x0b)
            and d[LEVEL] in (0, 1) and d[HOOK:HOOK + 6] == bytes.fromhex('558bec83e4f8') and not any(d[CAVE:CAVE + 0x80]))

LOADER_STUB = CAVE + 0x80          # pushad; LoadLibraryA("ISModLoader.dll"); popad; jmp CAVE  (the menu hook goes here first)
LOADER_NAME = CAVE + 0xa0
IAT_LOADLIBRARYA = 0x5320b4
VA = lambda off: 0x400000 + off      # .text file offsets == RVAs in this exe

def has_loader(d):
    return d[LOADER_STUB] == 0x60 and d[LOADER_NAME:LOADER_NAME + 15] == b'ISModLoader.dll'

def patch(d):
    d = bytearray(d)
    d[PAGE] = 0x0a; d[LEVEL] = 0
    d[CAVE:CAVE + len(CODE)] = CODE
    d[CAVE + 0x60:CAVE + 0x6a] = b'solo.flag\0'
    stub = b'\x60\x68' + struct.pack('<I', VA(LOADER_NAME)) + b'\xff\x15' + struct.pack('<I', IAT_LOADLIBRARYA) + b'\x61'
    stub += b'\xe9' + struct.pack('<i', CAVE - (LOADER_STUB + len(stub) + 5))
    d[LOADER_STUB:LOADER_STUB + len(stub)] = stub
    d[LOADER_NAME:LOADER_NAME + 16] = b'ISModLoader.dll\0'
    d[HOOK:HOOK + 6] = b'\xe9' + struct.pack('<i', LOADER_STUB - (HOOK + 5)) + b'\x90'
    return bytes(d)

def patched_exe(game, weapons=None):
    """-> (exe, temporary). With weapon tweaks, or when Game.exe is stock, a patched copy ISModGame.exe is made from the
    stock bytes (Game.exe or Game.exe.orig) and deleted by the launcher afterwards. Game.exe itself is never changed."""
    exe = os.path.join(game, 'Game.exe')
    if not os.path.exists(exe): raise RuntimeError('Game.exe not found in %s (put ISModLauncher in the Iron Storm folder)' % game)
    d = open(exe, 'rb').read()
    if is_patched(d) and has_loader(d) and not weapons: return exe, False
    if not is_stock(d):
        o = exe + '.orig'
        d = open(o, 'rb').read() if os.path.exists(o) else b''
        if not is_stock(d): raise RuntimeError('Game.exe is not the v1.041 version this launcher supports (update the game to 1.04)')
    copy = os.path.join(game, COPY)
    open(copy, 'wb').write(apply_weapons(patch(d), weapons))
    return copy, True
