"""Mod packages for the launcher, kept in <Iron Storm>\\Mods\\ as a folder or a .zip (same layout either way):

  mod.json              {"title": "...", "description": "...", "author": "...", "levels": {"test": {}, "lv2": {}},
                         "multiplayer": {"isdm5": {}}, "weapons": {...}}   (weapons: optional, see gamepatch.py)
  preview.png           optional screenshot shown in the launcher (.png; .jpg/.gif too if Pillow is installed)
  sounds/*              loose sound files (.wav) used by the mod's maps (ambient_sound / music), or replacing stock sounds of the same name
  models/*              loose model files (weapons, characters, pickups ... any .4x3/.4xt, e.g. handgun_first.4x3): while the mod
                        runs they override the stock model of the same name (ISModLoader loose files); nothing in Models.ibf changes
  <slot>/models/*       files that go into Models.ibf (<slot>.4x3, <slot>_light.4x3, <slot>_event_boxes.4X3, and
                        wiz_model_first.4x3 = first-person arms when the level's player_model has arms; the first level's win)
  <slot>/level/*        level script + nav graph (test.* -> levels\\multi\\test, lvN.* -> levels\\campaign\\levelN)
  mp/<name>/models|level   a multiplayer map (added, or replacing a stock one) -> levels\\multi\\<name>

A zip may also hold everything inside one top folder (mymod.zip -> mymod/mod.json ...).
"""
import os, json, shutil, zipfile
from ismap import bigfile

ARMS = {'kasakh': 'kasakh_model_first.4x3', 'lobby': 'Lobby_model_first.4x3', 'russian': 'russian_model_first.4x3',
        'sibbourrin1': 'sibbourrin1_model_first.4x3', 'sibsniper': 'sibsniper_model_first.4x3',
        'supercadet': 'supercadet_model_first.4x3', 'trooper': 'trooper_model_first.4x3', 'wiz': 'wiz_model_first.4x3'}
ARMS_FILE = 'wiz_model_first.4x3'
PREVIEWS = ('preview.png', 'preview.gif', 'preview.jpg', 'preview.jpeg', 'screenshot.png', 'screenshot.jpg')

def mods_dir(game): return os.path.join(game, 'Mods')

def stock_archive(game):
    ibf, lst = os.path.join(game, 'Models.ibf'), os.path.join(game, 'Models.lst')
    return (ibf + '.bak', lst + '.bak') if os.path.exists(ibf + '.bak') else (ibf, lst)

def arms_data(game, player_model):
    si, sl = stock_archive(game)
    return bigfile.read_file(si, sl, ARMS.get(player_model or '', ARMS['wiz']))

def level_dir(game, slot, mp=False):
    if mp: return os.path.join(game, 'levels', 'multi', slot)
    return os.path.join(game, 'levels', 'multi', 'test') if slot == 'test' else os.path.join(game, 'levels', 'campaign', 'level' + slot[2:])

class Source:
    """Read files of a mod by relative path ('lv2/level/lv2.gex'), from a folder or a zip."""
    def __init__(self, path):
        self.path = path; self.zip = None; self.prefix = ''
        if path.lower().endswith('.zip'):
            self.zip = zipfile.ZipFile(path)
            names = self.zip.namelist()
            if 'mod.json' not in names:
                tops = [n for n in names if n.endswith('/mod.json') and n.count('/') == 1]
                if not tops: raise ValueError('%s has no mod.json' % os.path.basename(path))
                self.prefix = tops[0][:-len('mod.json')]
    def read(self, rel):
        if self.zip:
            try: return self.zip.read(self.prefix + rel)
            except KeyError: return None
        p = os.path.join(self.path, *rel.split('/'))
        return open(p, 'rb').read() if os.path.isfile(p) else None
    def listdir(self, rel):
        if self.zip:
            pre = self.prefix + rel.rstrip('/') + '/'
            return [n[len(pre):] for n in self.zip.namelist() if n.startswith(pre) and n != pre and '/' not in n[len(pre):]]
        p = os.path.join(self.path, *rel.split('/'))
        return [f for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))] if os.path.isdir(p) else []
    def info(self):
        try: return json.loads(self.read('mod.json').decode('utf-8-sig'))
        except json.JSONDecodeError as e:
            raise ValueError('mod.json has a typo at line %d (%s). A missing or extra comma at the end of line %d or %d is the usual cause.' % (e.lineno, e.msg, max(1, e.lineno - 1), e.lineno))
    def preview(self):
        for n in PREVIEWS:
            d = self.read(n)
            if d: return n, d
        return None, None

def write(game, mod, slot, models, level, player_model=None, title=None, description=None, mp=False, sounds=None):
    """Save one compiled level into Mods\\<mod>\\ (a folder). models: {name: bytes}; level: {file name: bytes}."""
    root = os.path.join(mods_dir(game), mod); base = os.path.join(root, 'mp', slot) if mp else os.path.join(root, slot)
    for sub, files in (('models', models), ('level', level)):
        d = os.path.join(base, sub)
        if os.path.isdir(d): shutil.rmtree(d)
        os.makedirs(d)
        for fn, data in files.items(): open(os.path.join(d, fn), 'wb').write(data)
    if sounds:      # loose sound files (.wav) for the whole mod: sounds/ (loaded from disk while the mod runs, like models/)
        d = os.path.join(root, 'sounds'); os.makedirs(d, exist_ok=True)
        for fn, data in sounds.items(): open(os.path.join(d, fn), 'wb').write(data)
    mj = os.path.join(root, 'mod.json')
    info = json.load(open(mj, encoding='utf-8')) if os.path.exists(mj) else {'title': mod, 'description': '', 'author': '', 'levels': {}}
    if title: info['title'] = title
    if description: info['description'] = description
    info.setdefault('levels', {}); info.setdefault('multiplayer', {})
    info['multiplayer' if mp else 'levels'][slot] = {}
    json.dump(info, open(mj, 'w', encoding='utf-8'), indent=2)
    return root

def make_zip(game, mod):
    """Mods\\<mod>\\ (folder) -> Mods\\<mod>.zip, ready to share."""
    root = os.path.join(mods_dir(game), mod); out = root + '.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(root):
            for f in fs:
                p = os.path.join(d, f); z.write(p, os.path.relpath(p, root).replace(os.sep, '/'))
    return out

KNOWN_KEYS = ('title', 'description', 'author', 'levels', 'multiplayer', 'weapons', 'campaign')

def check_info(info):
    """-> list of problems in a mod.json (unknown keys, bad weapon settings, no levels), empty when it looks fine."""
    from . import gamepatch
    out = []
    if not isinstance(info, dict): return ['mod.json must be an object { ... }']
    for k in info:
        if k not in KNOWN_KEYS and k not in ('id', 'path', 'broken', 'warnings'): out.append('unknown key %r in mod.json (known: %s)' % (k, ', '.join(KNOWN_KEYS)))
    if not info.get('levels') and not info.get('multiplayer'): out.append('the mod has no levels and no multiplayer maps')
    try: gamepatch.check_weapons(info.get('weapons'))
    except ValueError as e: out.append(str(e))
    return out

def list_mods(game):
    """-> [dict(id, path, info...)] for every folder or .zip in Mods that has a mod.json. A folder wins over a zip of the same name."""
    out = {}; md = mods_dir(game)
    if not os.path.isdir(md): return []
    for f in sorted(os.listdir(md)):
        p = os.path.join(md, f)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, 'mod.json')): key = f
        elif f.lower().endswith('.zip'): key = f[:-4]
        else: continue
        if key in out and os.path.isdir(out[key]['path']): continue
        try: info = Source(p).info()
        except Exception as e: info = {'title': key, 'description': 'Cannot read this mod: %s' % e, 'levels': {}, 'broken': True}
        if not info.get('broken'):
            try: info['warnings'] = check_info(info)
            except Exception as e: info['warnings'] = [str(e)]
        info.update(id=key, path=p); out[key] = info
    return sorted(out.values(), key=lambda m: m.get('title', m['id']).lower())

OVERRIDE_DIR = 'ismod_override'

def install_loose(game, path):
    """Tell the loader where the mod's loose files are (models/ and sounds/): a folder mod is read in place;
    a zip mod is unpacked to <game>\\ismod_override first. Returns the paths to delete when the game closes."""
    src = Source(path)
    names = [('models', f) for f in src.listdir('models') if f.lower().endswith(('.4x3', '.4xt', '.wav'))]
    names += [('sounds', f) for f in src.listdir('sounds') if f.lower().endswith('.wav')]
    if not names: return []
    lst = os.path.join(game, 'ismod_override.txt')
    if not src.zip:
        dirs = [os.path.join(os.path.abspath(path), sub) + '\\' for sub in ('sounds', 'models') if any(n[0] == sub for n in names)]
        open(lst, 'w').write('\n'.join(dirs) + '\n')
        return [lst]
    d = os.path.join(game, OVERRIDE_DIR); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    for sub, f in names: open(os.path.join(d, f), 'wb').write(src.read(sub + '/' + f))
    open(lst, 'w').write(OVERRIDE_DIR + '\\\n')
    return [d, lst]

def install(game, path):
    """Put a mod's levels and arms into the game. Returns the slots installed."""
    ibf, lst = os.path.join(game, 'Models.ibf'), os.path.join(game, 'Models.lst')
    src = Source(path); info = src.info(); files = {}
    paths = []
    ad = arms_data(game, 'wiz')
    if ad is not None: files[ARMS_FILE] = ad                       # normal arms unless the first level brings its own
    order = sorted(info['levels'], key=lambda sl: sl == 'test')   # Test slot (the first level) last, so its arms win
    for slot in order:
        for fn in src.listdir(slot + '/models'):
            if fn.lower() != ARMS_FILE.lower(): files[fn] = src.read(slot + '/models/' + fn)   # arms now come from <level>.ismod at load time
        # Levels stay out of the game's levels folder: they go to ismod_levels\<slot> and the ISModLoader redirects the game there
        dest = os.path.join(game, 'ismod_levels', slot); os.makedirs(dest, exist_ok=True)
        for fn in src.listdir(slot + '/level'): open(os.path.join(dest, fn), 'wb').write(src.read(slot + '/level/' + fn))
        base = 'ismod_levels\\%s\\%s' % (slot, 'test' if slot == 'test' else slot)
        paths.append(('test=' if slot == 'test' else 'campaign %s=' % slot[2:]) + base)
    for name in info.get('multiplayer', {}):
        pre = 'mp/' + name
        for fn in src.listdir(pre + '/models'): files[fn] = src.read(pre + '/models/' + fn)
        dest = level_dir(game, name, mp=True)
        if not os.path.isdir(dest):
            os.makedirs(dest); open(os.path.join(dest, '.ismod_created'), 'w').close()
        for fn in src.listdir(pre + '/level'):
            tgt = os.path.join(dest, fn)
            if os.path.exists(tgt) and not os.path.exists(tgt + '.stock'): shutil.copy2(tgt, tgt + '.stock')
            elif not os.path.exists(tgt): open(os.path.join(dest, '.ismod_added'), 'a').write(fn + '\n')
            open(tgt, 'wb').write(src.read(pre + '/level/' + fn))
    bigfile.replace_files(ibf, lst, files)
    if paths: open(os.path.join(game, 'ismod_paths.txt'), 'w').write('\n'.join(paths) + '\n')
    return list(info['levels']) + ['mp:' + n for n in info.get('multiplayer', {})]

def restore(game, slots):
    """Undo install(): stock campaign levels and the normal arms come back; level folders the mod created are removed."""
    ibf, lst = os.path.join(game, 'Models.ibf'), os.path.join(game, 'Models.lst')
    si, sl = stock_archive(game); files = {}
    shutil.rmtree(os.path.join(game, 'ismod_levels'), ignore_errors=True)
    try: os.remove(os.path.join(game, 'ismod_paths.txt'))
    except OSError: pass
    for slot in slots:
        mp = slot.startswith('mp:'); slot = slot[3:] if mp else slot
        dest = level_dir(game, slot, mp)
        if not mp:      # campaign levels are redirected (ismod_levels), nothing in levels\\ was changed; only the model archive is restored
            for fn in (slot + '.4x3', slot + '_light.4x3', slot + '_event_boxes.4X3'):
                d = bigfile.read_file(si, sl, fn)
                if d is not None: files[fn] = d
            continue
        if os.path.exists(os.path.join(dest, '.ismod_created')):
            shutil.rmtree(dest, ignore_errors=True); continue
        for fn in os.listdir(dest):
            if fn.endswith('.stock'): shutil.copyfile(os.path.join(dest, fn), os.path.join(dest, fn[:-6]))
        for fn in os.listdir(dest):
            if fn.endswith('.stock'): os.remove(os.path.join(dest, fn))
        added = os.path.join(dest, '.ismod_added')
        if os.path.exists(added):
            for fn in open(added).read().split():
                try: os.remove(os.path.join(dest, fn))
                except OSError: pass
            os.remove(added)
        for fn in (slot + '.4x3', slot + '_light.4x3', slot + '_event_boxes.4X3'):
            d = bigfile.read_file(si, sl, fn)
            if d is not None: files[fn] = d
    ad = arms_data(game, 'wiz')
    if ad is not None: files[ARMS_FILE] = ad
    bigfile.replace_files(ibf, lst, files)
