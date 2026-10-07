"""Build a whole mod from one folder of maps.

The folder (e.g. trenchbroom\\maps\\mymod\\) holds the .map files (+ their .script files), an optional preview.png,
and a mod.json that says which map goes where:

  {
    "title": "My mod",
    "description": "What it is about.",
    "author": "me",
    "campaign": ["start.map", "bunker.map", "escape.map"],      first map = first level, then level 2, 3 ...
    "multiplayer": {"isdm5": "arena.map", "isdm1": "remake.map"},   add a map, or replace a stock one, by name
    "weapons": {"smg": {"damage": 12}}                         optional, see README
  }

A models\\ subfolder (.4x3 files, e.g. a replacement handgun_first.4x3 exported from Blender) overrides the stock models
while the mod runs. A plugins\\ subfolder (C/C++ sources and/or ready DLLs) is compiled into the mod too (see modtools\\sdk).

Usage:  python build_mod.py FOLDER          (TrenchBroom: compile profile "Build mod")
Result: <Iron Storm>\\Mods\\<folder name>\\, ready for ISModLauncher. In scripts, "end_level next" goes to the next
campaign map (credits after the last one), and so does a trigger_end with next = next.
"""
import os, sys, json, shutil, subprocess, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from ismap import modpack
GAME = os.environ.get('ISMOD_GAME') or os.path.dirname(HERE)

def main():
    if len(sys.argv) != 2: print(__doc__); return 1
    src = os.path.abspath(sys.argv[1])
    if os.path.isfile(src): src = os.path.dirname(src)        # a map file was given: use its folder
    mj = os.path.join(src, 'mod.json')
    if not os.path.exists(mj): sys.exit('no mod.json in %s (see build_mod.py for the format)' % src)
    try: cfg = json.load(open(mj, encoding='utf-8'))
    except ValueError as e: sys.exit('mod.json: %s' % e)
    mod = os.path.basename(src.rstrip('\\/'))
    camp = cfg.get('campaign', []); mp = cfg.get('multiplayer', {})
    if not camp and not mp: sys.exit('mod.json: list maps under "campaign" and/or "multiplayer"')
    if len(camp) > 20: sys.exit('mod.json: at most 20 campaign maps')
    for n in mp:
        if not re.fullmatch(r'[A-Za-z0-9_]{1,16}', n) or n.lower() == 'test' or re.fullmatch(r'lv\d+', n.lower()):
            sys.exit('mod.json: bad multiplayer map name %r (letters/digits, not test or lvN)' % n)
    jobs = []
    for i, m in enumerate(camp):
        slot = 'test' if i == 0 else 'lv%d' % (i + 1)
        nxt = 0 if i == len(camp) - 1 else i + 2
        jobs.append((m, slot, ['--next', str(nxt)]))
    for n, m in mp.items(): jobs.append((m, n, []))
    for m, _, _ in jobs:
        if not os.path.exists(os.path.join(src, m)): sys.exit('mod.json: map file not found: %s' % m)
    out = os.path.join(modpack.mods_dir(GAME), mod)
    if os.path.isdir(out): shutil.rmtree(out)                  # rebuild from scratch
    for m, slot, extra in jobs:
        print('=== %s -> %s' % (m, slot), flush=True)
        r = subprocess.call([sys.executable, os.path.join(HERE, 'map2is.py'), os.path.join(src, m), '--name', slot,
                             '--package', mod] + extra, cwd=HERE)
        if r: sys.exit('building %s failed' % m)
    info = json.load(open(os.path.join(out, 'mod.json'), encoding='utf-8'))
    for k in ('title', 'description', 'author', 'weapons'):
        if k in cfg: info[k] = cfg[k]
    info.setdefault('title', mod)
    json.dump(info, open(os.path.join(out, 'mod.json'), 'w', encoding='utf-8'), indent=2)
    psrc = os.path.join(src, 'plugins')              # plugins: ready DLLs and/or C/C++ sources
    if os.path.isdir(psrc):
        from ismap import plugins
        pout = os.path.join(out, 'plugins'); os.makedirs(pout, exist_ok=True)
        for f in os.listdir(psrc):
            if f.lower().endswith('.dll'): shutil.copyfile(os.path.join(psrc, f), os.path.join(pout, f))
        plugins.compile_dir(psrc, os.path.join(pout, mod + '.dll'))
    msrc = os.path.join(src, 'models')               # loose models (weapons, characters ...): shipped as they are, no repacking
    if os.path.isdir(msrc):
        mout = os.path.join(out, 'models'); os.makedirs(mout, exist_ok=True)
        for f in os.listdir(msrc):
            if f.lower().endswith(('.4x3', '.4xt')): shutil.copyfile(os.path.join(msrc, f), os.path.join(mout, f))
        print('loose models: %s' % ', '.join(sorted(os.listdir(mout))))
    for f in os.listdir(src):
        if f.lower() in modpack.PREVIEWS: shutil.copyfile(os.path.join(src, f), os.path.join(out, f.lower()))
    print('built mod %r: %d campaign map(s), %d multiplayer map(s) -> %s' % (info['title'], len(camp), len(mp), out))
    return 0

if __name__ == '__main__':
    sys.exit(main())
