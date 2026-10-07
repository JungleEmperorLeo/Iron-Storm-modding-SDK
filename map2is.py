#!/usr/bin/env python3
"""Convert a Trenchbroom .map into an Iron Storm multiplayer map and (optionally) install it.

usage:
  python map2is.py MAP_FILE [--name isdm5] [--install] [--game GAME_DIR] [--textures DIR]
  (GAME_DIR defaults to the folder above modtools)

Writes modtools\\build\\<name>\\ (the .4x3 files and the level scripts). With --install it also
puts them into Models.ibf / levels\\multi\\<name>\\ (re-running replaces the previous version).

Entities (see trenchbroom\\IronStorm.fgd):
  info_player_deathmatch  spawn point (up to 32). keys: angle, team (1/2, team deathmatch). team 1/2 = USWE/Russian
  info_player_team1/2     capture-the-flag spawn for the USWE / Russian side (keys: angle)
  npc_soldier             enemy soldier, single player only (keys: angle, weapon, model, health, behavior stand/chase/patrol, target)
  npc_friend              friendly level-1 character (keys: angle, who cecile/mitchel, behavior follow/stand, distance)
  info_player_start       single-player start for the 'test' export (keys: angle)
  item_armory             weapon crate (up to 6). keys: angle, loadout (1-6)
  info_camera_spawn       camera before you spawn. keys: angle, pitch
  light_sun               position of the sun lens flare
  env_fog                 map fog (single player; up to 8, the first starts on, switch with trigger_weather enter_fog/exit_fog). keys: targetname, color (r g b 0-1 or 0-255), near, far, height_a, height_b
  info_drt                D.R.T. computer (single player). keys: angle, movie (stock D.R.T. movie names, up to 6), time
  info_document           readable document (single player). keys: angle, text (Trad text id, e.g. XX1DOCU002)
  npc_turret              automatic machine-gun turret (single player). keys: angle, yaw_min, yaw_max, rate, health, active
  npc_dog                 attack dog (single player). keys: angle, explosive, range, health, damage
  npc_helicopter          helicopter (single player). keys: kind allies/enemy, targetname; steered by script heli_* commands
  weapon_mounted_mg       mounted machine gun the player can use (single player). keys: angle
  prop_static             a stock model placed in the level (single player). keys: model (e.g. OBJ_bidon), angles, mode (static/breakable), node
  env_particle            steam / gas effect (single player). keys: effect (steam, gas, gas_small), scale, angles
  light                   point light. keys: _color (r g b 0-255), light (intensity, default 1), range (default 400), start (default 0)
  ambient_wind            wind sound (up to 2)
  worldspawn              key 'sky' (default sky_LV_01)
Special textures (any folder): clip / nodraw / caulk / sky = solid but not drawn,
  skip / trigger / hint / origin = ignored entirely. Everything else is drawn and solid.
"""
import math, os, sys, argparse, re, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ismap import mapfile, scene, bigfile
from ismap.gex import Gex
from ismap.repack import write_map

SURFACE_NAMES = {'ground': 1, 'rock': 3, 'wood': 2, 'metal': 4, 'water': 7, 'snow': 8}   # unverified guess; override with "@name = number" in surfaces.txt

def surface_for(tname, rules, default):
    low = tname.lower(); base = low.split('/')[-1]
    if base.startswith('surf') and base[4:].isdigit(): return int(base[4:])
    for pat, val in rules:
        if pat in low: return val
    return default

def load_material_rules(*paths):
    """materials.txt: one rule per line, '#' starts a comment:   texture_pattern = kind [opacity]
       kind: opaque, cut (alpha holes), blend (translucent, lit), reflect / reflect_bright (translucent + environment reflection),
       add (additive glow). opacity 0-1 is optional (blend, reflect, add). The pattern is a texture name (folder/name or just name) with * allowed.
       Rules in later files and later lines win (modtools\\materials.txt first, then the one next to the map)."""
    import fnmatch
    rules = []
    for path in paths:
        if not os.path.exists(path): continue
        for ln in open(path, encoding='utf-8', errors='replace'):
            ln = ln.split('#', 1)[0].strip()
            if not ln: continue
            if '=' not in ln: print('materials.txt: ignored line (no "="):', ln); continue
            pat, val = (x.strip() for x in ln.split('=', 1)); w = val.split()
            if not w or w[0].lower() not in scene.KINDS: print('materials.txt: unknown kind in: %s   (known: %s)' % (ln, ', '.join(scene.KINDS))); continue
            op = None
            if len(w) > 1:
                try: op = float(w[1]); assert 0 <= op <= 1
                except (ValueError, AssertionError): print('materials.txt: opacity must be 0-1 in:', ln); continue
            rules.append((pat.lower().replace('\\', '/'), w[0].lower() + ('@%g' % op if op is not None else '')))
    def lookup(tname):
        t = tname.lower().replace('\\', '/'); b = t.split('/')[-1]; hit = None
        for pat, kind in rules:
            if fnmatch.fnmatch(t, pat) or fnmatch.fnmatch(b, pat) or fnmatch.fnmatch(t.rsplit('.', 1)[0], pat) or fnmatch.fnmatch(b.rsplit('.', 1)[0], pat): hit = kind
        return hit
    lookup.count = len(rules)
    return lookup

def load_surface_rules(path):
    """surfaces.txt, three kinds of lines (# starts a comment):
         @metal = 2        defines/overrides the number behind a surface name
         wood =            starts a block: every following line is a texture (or part of a texture name) with that surface
           lv3_bois
           planks
         grate = metal     one-line rule"""
    names = dict(SURFACE_NAMES); raw = []; block = None
    if os.path.exists(path):
        for ln in open(path, encoding='latin1'):
            ln = ln.split('#')[0].strip()
            if not ln: continue
            if '=' in ln:
                a, b = [x.strip().lower() for x in ln.split('=', 1)]
                if a.startswith('@'):
                    try: names[a[1:]] = int(b)
                    except ValueError: print('surfaces.txt: bad line (number expected):', ln)
                elif b == '': block = a
                else: raw.append((a, b, ln)); block = None
            elif block: raw.append((ln.lower(), block, ln))
            else: print('surfaces.txt: ignored line outside a block:', ln)
    rules = []
    for a, b, ln in raw:
        if b in names: rules.append((a, names[b]))
        elif b.isdigit(): rules.append((a, int(b)))
        else: print('surfaces.txt: unknown surface "%s" for: %s   (known: %s)' % (b, ln, ', '.join(sorted(names)))); names[b] = names.get(b, -1)
    return rules

NOT_DRAWN = {'clip', 'nodraw', 'caulk', 'sky', 'playerclip'}
IGNORED = {'skip', 'trigger', 'hint', 'hintskip', 'origin', 'null'}
TEMPLATE = 'isdm3'
CTF_TEMPLATE = 'isctf3'   # the stock CTF level without doors, levers or timers

def pow2(n, lo=4, hi=512):
    p = lo
    while p < n and p < hi: p *= 2
    return p

EXTS = ('.png', '.jpg', '.jpeg', '.tga', '.bmp')
_index = None
def load_texture(tex_dirs, name):
    """exact path first (textures/<folder>/<name>.png), then any folder with that file name"""
    global _index
    from PIL import Image
    for d in tex_dirs:
        for ext in EXTS:
            p = os.path.join(d, *name.split('/')) + ext
            if os.path.exists(p):
                im = Image.open(p).convert('RGBA'); return im, im.size
    if _index is None:
        _index = {}
        for d in tex_dirs:
            for root, _, files in os.walk(d):
                for f in files:
                    b, e = os.path.splitext(f)
                    if e.lower() in EXTS: _index.setdefault(b.lower(), os.path.join(root, f))
    p = _index.get(name.split('/')[-1].lower())
    if p:
        print('  texture %s -> %s' % (name, p))
        im = Image.open(p).convert('RGBA'); return im, im.size
    return None, None

YAW_OFFSET = 180.0   # game facing = Trenchbroom angle + this (measured on the armory crate)

def angle_props(yaw):
    yaw = yaw + YAW_OFFSET
    z = (yaw + 180) % 360 - 180
    f = (yaw - 90 + 180) % 360 - 180
    return z, f

SCALE = 1.0
FLAG_LIFT = 14.0      # game units: the flag model is a flat cloth whose origin is 13.4 units above its bottom edge
ARMORY_LIFT = 12.0   # game units: the crate model's origin is its centre, so lift it by half its height

def vec(s): return [float(x) * SCALE for x in s.split()]

def sc(p): return tuple(x * SCALE for x in p)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('map'); ap.add_argument('--game', default=os.environ.get('ISMOD_GAME') or os.path.dirname(HERE))
    ap.add_argument('--name'); ap.add_argument('--install', action='store_true')
    ap.add_argument('--textures', action='append', default=[])
    ap.add_argument('--out')
    ap.add_argument('--package', help='single player: also save the level into mods\\PACKAGE for the launcher')
    ap.add_argument('--title', help='mod title shown in the launcher (with --package)')
    ap.add_argument('--next', type=int, help='level number that "next" means (end_level next, trigger_end next); build_mod.py sets it')
    ap.add_argument('--description', help='mod description shown in the launcher (with --package)')
    a = ap.parse_args()
    name = (a.name or os.path.splitext(os.path.basename(a.map))[0]).lower()
    if len(name) > 40 or not name.replace('_', '').isalnum(): sys.exit('map name must be letters/digits/underscore: ' + name)
    game = a.game
    ibf, lst = os.path.join(game, 'Models.ibf'), os.path.join(game, 'Models.lst')
    tex_dirs = a.textures + [os.path.join(os.path.dirname(os.path.abspath(a.map)), '..', 'textures'),
                             os.path.join(os.path.dirname(os.path.abspath(a.map)), 'textures'),
                             os.path.join(HERE, 'trenchbroom', 'textures')]

    ents = mapfile.parse(open(a.map, encoding='latin1').read())
    world = ents[0]['props']
    global SCALE
    SCALE = float(world.get('scale', 0.375))
    print('scale: 1 map unit = %g game units' % SCALE)
    # ---------------- geometry
    render, collide, textures, sizes, missing = [], [], {}, {}, set()
    surf_rules = load_surface_rules(os.path.join(HERE, 'surfaces.txt')); surf_report = {}
    print('surface rules: %d from %s' % (len(surf_rules), os.path.join(HERE, 'surfaces.txt')))
    game_tex = {}
    sector_boxes = []; solid_brushes = []; floor_polys = []; water_boxes = []
    solo_early = name == 'test' or re.fullmatch(r'lv([2-9]|1[0-9]|20)', name) is not None
    water_ents = {}; water_imgs = {}; water_models = {}      # func_water with the engine's WATER entity (single player): surface triangles per entity, textures, finished models
    for e in ents:
        cls = e['props'].get('classname', '')
        if cls == 'func_sector':        # each brush is a room: only its bounding box is used
            for brush in e['brushes']:
                pts = [p for f, n, poly in mapfile.brush_polygons(brush) for p in poly]
                if pts: sector_boxes.append(([min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]))
            continue
        if e is not ents[0] and not cls.startswith('func_'): continue
        is_water = cls == 'func_water'     # water surface: only the top faces, drawn translucent from both sides, not solid
        water_fx = is_water and solo_early and str(e['props'].get('effect', '1')).strip().lower() not in ('0', 'no', 'false', 'off')   # single player: a real WATER entity (rippling surface) instead of a flat plane
        R, C = render, collide
        for brush in e['brushes']:
            bpolys = mapfile.brush_polygons(brush)
            if is_water:
                pts = [p for f, n, poly in bpolys for p in poly]
                water_boxes.append((sc([min(p[i] for p in pts) for i in range(3)]), sc([max(p[i] for p in pts) for i in range(3)])))
            elif any(f['tex'].split('/')[-1].lower() not in IGNORED for f, n, poly in bpolys):
                pts = [p for f, n, poly in bpolys for p in poly]
                solid_brushes.append(([(n, sum(n[i] * poly[0][i] for i in range(3))) for f, n, poly in bpolys],
                                      [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]))
                floor_polys.extend(poly for f, n, poly in bpolys if n[2] > 0.7)
            for f, n, poly in bpolys:
                if is_water and n[2] < 0.7: continue
                tname = f['tex']; base = tname.split('/')[-1].lower()
                if base in IGNORED or base.startswith('*'): continue
                if water_fx:
                    if tname not in water_imgs:
                        im, size = load_texture(tex_dirs, tname)
                        if im is None:
                            missing.add(tname); from PIL import Image; im = Image.new('RGB', (64, 64), (255, 0, 255)); size = (64, 64)
                        water_imgs[tname] = (im.resize((pow2(im.size[0]), pow2(im.size[1]))), size)
                    w_, h_ = water_imgs[tname][1]
                    wt = water_ents.setdefault(id(e), dict(props=e['props'], tex=tname, tris=[]))
                    for t in [(poly[0], poly[k], poly[k+1]) for k in range(1, len(poly) - 1)]:
                        wt['tris'].append((tuple(sc(p) for p in t), tuple(mapfile.face_uv(f, n, p, w_, h_) for p in t)))
                    continue
                key = tname + ('|water' if is_water else '')
                tris = [(poly[0], poly[k], poly[k+1]) for k in range(1, len(poly) - 1)]
                if not is_water:
                    sv = surface_for(tname, surf_rules, int(world.get('_surface', 3)))
                    if tname not in surf_report: surf_report[tname] = sv
                    for t in tris: C.append((tuple(sc(p) for p in t), n, sv))
                    if base in NOT_DRAWN: continue
                if key not in sizes:
                    im, size = load_texture(tex_dirs, tname)
                    if im is None:
                        missing.add(tname); sizes[key] = (64, 64); im = None
                    else: sizes[key] = size
                    gname = tname.split('/')[-1].replace(' ', '_')[:50] + '.tga'
                    if is_water: gname = 'glass_' + gname        # the scene writer draws textures with 'glass' in the name translucent
                    while gname.lower() in {g.lower() for g in game_tex.values()}: gname = '_' + gname
                    game_tex[key] = gname
                    if im is None:
                        from PIL import Image
                        im = Image.new('RGB', (64, 64), (255, 0, 255))
                    textures[gname] = im.resize((pow2(im.size[0]), pow2(im.size[1])))
                w, h = sizes[key]
                for t in tris:
                    uvs = tuple(mapfile.face_uv(f, n, p, w, h) for p in t)
                    R.append((game_tex[key], tuple(sc(p) for p in t), uvs, n))
                    if is_water:        # the same triangle seen from below
                        R.append((game_tex[key], tuple(sc(p) for p in (t[0], t[2], t[1])), (uvs[0], uvs[2], uvs[1]), tuple(-x for x in n)))
    if water_boxes:      # floors under the water get the water surface (footsteps, impacts)
        wet = 0
        for i, (tri, n, sv) in enumerate(collide):
            if n[2] < 0.7: continue
            cx, cy, cz = [sum(p[k] for p in tri) / 3 for k in range(3)]
            if any(lo[0] <= cx <= hi[0] and lo[1] <= cy <= hi[1] and lo[2] - 1 <= cz <= hi[2] for lo, hi in water_boxes):
                collide[i] = (tri, n, 7); wet += 1
        print('water: %d volumes, %d floor triangles made wet' % (len(water_boxes), wet))
    for tn, sv in sorted(surf_report.items()): print('  surface %2d  %s' % (sv, tn))
    if missing: print('WARNING: textures not found (drawn magenta):', ', '.join(sorted(missing)))
    print('geometry: %d drawn triangles, %d solid triangles, %d textures' % (len(render), len(collide), len(textures)))
    # ---------------- lighting: vertex colours baked from `light` entities (the game's world is vertex lit)
    lamps = [e['props'] for e in ents[1:] if e['props'].get('classname') == 'light']
    vcol = None
    if lamps:
        amb = int(float(ents[0]['props'].get('ambient', 64)))
        grid = float(ents[0]['props'].get('lightgrid', 192)) * SCALE
        def lcol(v):
            c = [float(x) for x in str(v).split()][:3] if v else [255, 255, 255]
            c = c + [255] * (3 - len(c))
            return [x / 255.0 if max(c) > 1.0 else x for x in c]
        L = [(vec(e.get('origin', '0 0 0')), lcol(e.get('_color')), float(e.get('light', 1.0)),
              float(e.get('start', 0)) * SCALE, max(1.0, float(e.get('range', 400)) * SCALE)) for e in lamps]
        def split(t):
            tex, p, uv, n = t
            d = [(math.dist(p[i], p[(i + 1) % 3]), i) for i in range(3)]
            ln, i = max(d)
            if ln <= grid: return [t]
            j = (i + 1) % 3; k = (i + 2) % 3
            mp = tuple((p[i][a] + p[j][a]) / 2 for a in range(3)); mu = tuple((uv[i][a] + uv[j][a]) / 2 for a in range(2))
            a = (tex, (p[i], mp, p[k]), (uv[i], mu, uv[k]), n); b = (tex, (mp, p[j], p[k]), (mu, uv[j], uv[k]), n)
            return split(a) + split(b)
        # occluders for shadows: the visible triangles before subdivision (game units)
        shadows = str(ents[0]['props'].get('shadows', '1')) != '0'
        occ = []
        for _, (t0, t1, t2), _, _ in render:
            e1 = [t1[i] - t0[i] for i in range(3)]; e2 = [t2[i] - t0[i] for i in range(3)]
            lo = [min(t0[i], t1[i], t2[i]) for i in range(3)]; hi = [max(t0[i], t1[i], t2[i]) for i in range(3)]
            occ.append((t0, e1, e2, lo, hi))
        def blocked(p, q):
            d = [q[i] - p[i] for i in range(3)]
            lo = [min(p[i], q[i]) for i in range(3)]; hi = [max(p[i], q[i]) for i in range(3)]
            for a, e1, e2, tlo, thi in occ:
                if tlo[0] > hi[0] or thi[0] < lo[0] or tlo[1] > hi[1] or thi[1] < lo[1] or tlo[2] > hi[2] or thi[2] < lo[2]: continue
                h = (d[1]*e2[2]-d[2]*e2[1], d[2]*e2[0]-d[0]*e2[2], d[0]*e2[1]-d[1]*e2[0])
                det = e1[0]*h[0] + e1[1]*h[1] + e1[2]*h[2]
                if abs(det) < 1e-9: continue
                inv = 1.0 / det; s = [p[i] - a[i] for i in range(3)]
                u = inv * (s[0]*h[0] + s[1]*h[1] + s[2]*h[2])
                if u < 0 or u > 1: continue
                qv = (s[1]*e1[2]-s[2]*e1[1], s[2]*e1[0]-s[0]*e1[2], s[0]*e1[1]-s[1]*e1[0])
                v = inv * (d[0]*qv[0] + d[1]*qv[1] + d[2]*qv[2])
                if v < 0 or u + v > 1: continue
                t = inv * (e2[0]*qv[0] + e2[1]*qv[1] + e2[2]*qv[2])
                if 1e-3 < t < 0.999: return True
            return False
        n0 = len(render)
        render = [x for t in render for x in split(t)]
        print('lighting: %d lights, %d -> %d triangles (grid %g, ambient %d)' % (len(L), n0, len(render), grid, amb))
        def vcol(p, nrm):
            acc = [amb / 255.0] * 3
            for pos, rgb, mul, st, en in L:
                d = [pos[a] - p[a] for a in range(3)]; dist = math.sqrt(sum(x * x for x in d)) or 1e-6
                if dist >= en: continue
                if shadows and blocked([p[a] + nrm[a] * 0.05 for a in range(3)], pos): continue
                nl = max(0.0, sum(d[a] / dist * nrm[a] for a in range(3)))
                fall = 1.0 if dist <= st else (en - dist) / (en - st)
                for a in range(3): acc[a] += mul * rgb[a] * nl * fall * 1.0
            r, g, b = [max(0, min(255, int(c * 255))) for c in acc]
            return 0xff000000 | (r << 16) | (g << 8) | b
    if str(world.get('_vcol_test', '0')) == '1':
        # diagnostic: split triangles and colour by side so we can see whether the game uses vertex colours at all
        def split2(t):
            tex, p, uv, n = t
            d = [(math.dist(p[i], p[(i + 1) % 3]), i) for i in range(3)]
            ln, i = max(d)
            if ln <= 72: return [t]
            j = (i + 1) % 3; k = (i + 2) % 3
            mp = tuple((p[i][a] + p[j][a]) / 2 for a in range(3)); mu = tuple((uv[i][a] + uv[j][a]) / 2 for a in range(2))
            return split2((tex, (p[i], mp, p[k]), (uv[i], mu, uv[k]), n)) + split2((tex, (mp, p[j], p[k]), (mu, uv[j], uv[k]), n))
        render = [x for t in render for x in split2(t)]
        print('VERTEX COLOUR TEST: x<0 = 0xffff0000, x>0 = 0xff0000ff (%d triangles)' % len(render))
        vcol = lambda p, nrm: 0xffff0000 if p[0] < 0 else 0xff0000ff
    sectors = portals = None
    if sector_boxes:
        from ismap import sectors as secmod
        for i in range(len(sector_boxes)):
            for j in range(i + 1, len(sector_boxes)):
                A, B = sector_boxes[i], sector_boxes[j]
                if all(min(A[1][k], B[1][k]) - max(A[0][k], B[0][k]) > 0.5 for k in range(3)):
                    print('WARNING: func_sector brushes %d and %d overlap; sectors must not overlap' % (i + 1, j + 1))
        def solid_at(p):
            for planes, lo, hi in solid_brushes:
                if all(lo[k] - 0.01 <= p[k] <= hi[k] + 0.01 for k in range(3)) and all(sum(n[k] * p[k] for k in range(3)) - d < -0.01 for n, d in planes): return True
            return False
        pmap = secmod.find_portals(sector_boxes, solid_at)
        sboxes = [(sc(b[0]), sc(b[1])) for b in sector_boxes]
        rr, cc, stray = secmod.partition(render, collide, sboxes)
        if stray: print('WARNING: %d triangles lie outside every func_sector (attached to the nearest one, unclipped)' % stray)
        keep = [i for i in range(len(sboxes)) if rr[i] and cc[i]]
        for i in range(len(sboxes)):
            if i not in keep: print('WARNING: func_sector %d has no geometry and is dropped' % (i + 1))
        remap = {old: new for new, old in enumerate(keep)}
        sectors = [dict(box=sboxes[i], render=rr[i], collide=cc[i]) for i in keep]
        portals = [dict(a=remap[p['a']], b=remap[p['b']], quad=[sc(q) for q in p['quad']], normal=p['normal'])
                   for p in pmap if p['a'] in remap and p['b'] in remap]
        linked = {p['a'] for p in portals} | {p['b'] for p in portals}
        for k in range(len(sectors)):
            if k not in linked and len(sectors) > 1: print('WARNING: sector %d has no portal to any other sector' % (keep[k] + 1))
        print('sectors: %d, portals: %d' % (len(sectors), len(portals)))
        for p in pmap: print('  portal sector %d <-> %d  %s' % (p['a'] + 1, p['b'] + 1, [round(x) for x in p['quad'][0]] + [round(x) for x in p['quad'][2]]))
    mat_rules = load_material_rules(os.path.join(HERE, 'materials.txt'), os.path.join(os.path.dirname(os.path.abspath(a.map)), 'materials.txt'))
    mat_over = {}
    for _k, _g in game_tex.items():
        _m = mat_rules(_k.split('|')[0])
        if _m and _g in textures: mat_over[_g] = _m
    if mat_over: print('materials: ' + ', '.join('%s=%s' % (g, m) for g, m in sorted(mat_over.items())))
    head, recs, tags, (mn, mx) = scene.build(render, collide, textures, name, vcolour=vcol, lit=vcol is not None, surface=int(world.get('_surface', 3)), glass=float(world.get('glass_opacity', 0.6)), sectors=sectors, portals=portals, materials=mat_over)

    # ---------------- entities -> level script
    def ents_of(*classes): return [e['props'] for e in ents[1:] if e['props'].get('classname') in classes]
    starts = ents_of('info_player_start')      # single-player start (campaign Test slot only)
    spawns = ents_of('info_player_deathmatch', 'info_player_team1', 'info_player_team2') or starts   # multiplayer spawns
    armories = ents_of('item_armory')
    lamps = ents_of('light'); cams = ents_of('info_camera_spawn'); suns = ents_of('light_sun'); winds = ents_of('ambient_wind')
    if not spawns: sys.exit('the map needs at least one info_player_deathmatch (or info_player_start)')
    if len(spawns) > 32: sys.exit('at most 32 spawn points (found %d)' % len(spawns))
    if len(armories) > 16: sys.exit('at most 16 item_armory (found %d)' % len(armories))
    flags = {int(e.get('team') or 0) or (1 if e.get('classname') == 'info_flag_team1' else 2): e for e in ents_of('info_flag_team1', 'info_flag_team2')}
    far = (0.0, 0.0, -30000.0)
    centre = [(mn[i] + mx[i]) / 2 for i in range(3)]

    tmpl_dir = os.path.join(game, 'levels', 'multi', TEMPLATE)
    outputs = {}
    modes = [('dm', TEMPLATE), ('tdm', TEMPLATE)]
    if 1 in flags and 2 in flags: modes.append(('ctf', CTF_TEMPLATE))
    elif flags: print('NOTE: capture-the-flag needs both info_flag_team1 and info_flag_team2; skipping the ctf script')
    SOLO = name == 'test' or re.fullmatch(r'lv([2-9]|1[0-9]|20)', name) is not None    # campaign slots: test (Test slot), lv2-lv20 (levels 2-20)
    NEXT = a.next if a.next is not None else (2 if name == 'test' else int(name[2:]) + 1 if SOLO else 0)   # 'next' level number
    SOLO_TURN = -90.0 if SOLO else 0.0   # single-player mode turns objects 90 degrees left of multiplayer
    for mode, tmpl in modes:
        ctf = mode == 'ctf'
        src = os.path.join(game, 'levels', 'multi', tmpl, '%s_%s.gex' % (tmpl, mode))
        g = Gex(open(src, 'rb').read())
        # spawn points: every template slot gets a real spawn (cycled), so nobody spawns outside the map
        rs = g.entities('id_respawn_')
        tcount = {}
        for k, ent in enumerate(rs):
            sp = spawns[k % len(spawns)]
            o = vec(sp.get('origin', '0 0 0')); yaw = float(sp.get('angle', 0))
            team = sp.get('team') or {'info_player_team1': '1', 'info_player_team2': '2'}.get(sp.get('classname'))
            if ctf:    # each template slot belongs to a team; hand it a spawn of that team
                tslot = 1 if '_uswe' in ent.lower() else 2
                pool = [s for s in spawns if (s.get('team') or {'info_player_team1': '1', 'info_player_team2': '2'}.get(s.get('classname'))) == str(tslot)] or spawns
                n_t = tcount.get(tslot, 0); tcount[tslot] = n_t + 1
                sp = pool[n_t % len(pool)]
                o = vec(sp.get('origin', '0 0 0')); yaw = float(sp.get('angle', 0)); team = tslot
            team = int(team) if team else (1 if k % 2 == 0 else 2)
            z, f1 = angle_props(yaw)
            g.set_prop(ent, '1+BASE_PROPERTY', o[0], o[1], o[2] + 1.0)   # +1: never start inside the floor
            g.set_prop(ent, '0+BASE_PROPERTY_RESPAWN', 90.0, 0.0, z)
            g.set_prop(ent, '1+BASE_PROPERTY_RESPAWN', f1)
            g.set_prop(ent, '3+BASE_PROPERTY_RESPAWN', team)
        # armories: loadout N = the weapons of template armory N
        arm = g.entities('id_armory_')
        used = {}
        for e in armories:
            want = int(e.get('loadout', 0) or 0)
            order = list(range(1, len(arm) + 1))
            if ctf and e.get('team') in ('1', '2'):    # prefer the half of the template slots that belongs to that team
                half = len(arm) // 2; order = (order[:half] + order[half:]) if e.get('team') == '1' else (order[half:] + order[:half])
            slot = want if 1 <= want <= len(arm) and want not in used else next((s for s in order if s not in used), None)
            if slot is None: print('WARNING: more item_armory than template slots (%d); extra ignored in %s' % (len(arm), mode)); continue
            used[slot] = e
        for s, ent in enumerate(arm, 1):
            e = used.get(s)
            o = vec(e.get('origin', '0 0 0')) if e else far
            if e: o[2] += ARMORY_LIFT
            g.set_prop(ent, '1+BASE_PROPERTY', *o)
            if e: g.set_prop(ent, '0+BASE_PROPERTY_ARMORY', (float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0)
        # camera
        if cams:
            c = cams[0]; o = vec(c.get('origin', '0 0 0')); yaw = float(c.get('angle', 0)); pitch = 90.0 - float(c.get('pitch', 15))
        else:
            o = [centre[0], centre[1], mx[2] - 16]; yaw = 0.0; pitch = 45.0
        z, f1 = angle_props(yaw)
        g.set_prop('id_position_camera_spawn', '1+BASE_PROPERTY', *o)
        g.set_prop('id_position_camera_spawn', '0+BASE_PROPERTY_POSITION', pitch, 0.0, z)
        g.set_prop('id_position_camera_spawn', '1+BASE_PROPERTY_POSITION', f1)
        g.set_prop('id_position_camera_spawn', '2+BASE_PROPERTY_POSITION', pitch)
        # ladder: the template has one ladder slot (stock: angle -90, value 12 for a 36-unit storey)
        lads = ents_of('info_ladder') if not ctf else None
        if str(world.get('_stock_ladder', '0')) == '1': lads = None   # diagnostic: keep the template ladder untouched
        if lads and len(lads) > 1: print('WARNING: only one info_ladder is supported for now; using the first')
        if lads is None: pass
        elif lads:
            L0 = lads[0]
            g.set_prop('id_ladder_ladder_school', '1+BASE_PROPERTY', *vec(L0.get('origin', '0 0 0')))
            g.set_prop('id_ladder_ladder_school', '1+BASE_PROPERTY_LADDER', (float(L0.get('angle', 0)) + 90 + 180) % 360 - 180)   # stock: facing -X (yaw 180) is stored as -90
            g.set_prop('id_ladder_ladder_school', '0+BASE_PROPERTY_LADDER', int(float(L0.get('rungs', 12))))
        else:
            g.set_prop('id_ladder_ladder_school', '1+BASE_PROPERTY', *far)
        if ctf:
            for ent in g.entities('id_ladder_') + g.entities('id_fixedgun_'): g.set_prop(ent, '1+BASE_PROPERTY', *far)
            for team, fe in flags.items():
                ent = 'id_flag_FLAG_001' if team == 1 else 'id_flag_FLAG_001_001'
                o = vec(fe.get('origin', '0 0 0')); o[2] += FLAG_LIFT + float(fe.get('height', 0) or 0) * SCALE
                g.set_prop(ent, '1+BASE_PROPERTY', *o)
        for k, ent in enumerate(g.entities('id_sound_wind') if ctf else ('id_sound_wind1', 'id_sound_wind2')):
            o = vec(winds[k]['origin']) if k < len(winds) else far
            g.set_prop(ent, '1+BASE_PROPERTY', *o)
        if suns: g.set_prop('id_lens_flare', '1+BASE_PROPERTY', *vec(suns[0]['origin']))
        sky = world.get('sky')
        if sky:
            for i, names in g.calls('set_sky'): g.set_const(i, 1, sky)
        outputs['%s_%s.gex' % (name, mode)] = g.tobytes()

    zones = []
    if SOLO:     # the campaign 'Test' slot loads levels\\multi\\test\\test.gex in single-player mode
        from ismap import solo
        donor = os.path.join(game, 'levels', 'campaign', 'level1', 'lv1.gex')
        if not os.path.exists(donor): sys.exit('single player needs ' + donor)
        sp = (starts or spawns)[0]; o = vec(sp.get('origin', '0 0 0')); yaw = float(sp.get('angle', 0))
        foes = [dict(pos=tuple(vec(e.get('origin', '0 0 0'))[:2]) + (vec(e.get('origin', '0 0 0'))[2] + 1.0,),
                     yaw=angle_props(float(e.get('angle', 0)))[1], weapon=e.get('weapon', 'smg') or 'smg',
                     model=e.get('model', 'russian') or 'russian', health=float(e.get('health', 60) or 60), tname=e.get('targetname') or None,
                     after=[(11, 1)] if str(e.get('hidden') or '0') in ('1', 'yes', 'true') else [])
                for e in ents_of('npc_soldier')]
        loadout = ammo = None             # worldspawn start_weapons / start_ammo
        if (world.get('start_weapons') or '').strip():
            loadout = set()
            for w in world['start_weapons'].replace(',', ' ').split():
                if w not in solo.LOADOUT_IDS: sys.exit('worldspawn start_weapons: unknown weapon %r (choices: %s)' % (w, ', '.join(solo.LOADOUT_IDS)))
                loadout.add(solo.LOADOUT_IDS[w])
        if (world.get('start_ammo') or '').strip():
            t = world['start_ammo'].replace(',', ' ').split(); ammo = {}
            if len(t) % 2: sys.exit('worldspawn start_ammo: give pairs like "mg 100 shotgun 20"')
            for w, v in zip(t[::2], t[1::2]):
                if w not in solo.AMMO_IDS or not v.isdigit(): sys.exit('worldspawn start_ammo: bad pair %r %r (ammo: %s)' % (w, v, ', '.join(solo.AMMO_IDS)))
                ammo[solo.AMMO_IDS[w]] = int(v)
        pm = world.get('player_model')
        if pm and pm not in solo.MODELS and pm not in solo.CHAR_MODELS: sys.exit('worldspawn player_model: unknown model %r' % pm)
        for f in foes:
            if f['model'] not in solo.MODELS and f['model'] not in solo.CHAR_MODELS:
                sys.exit('npc_soldier: unknown model %r (choices: %s)' % (f['model'], ', '.join(sorted(set(solo.MODELS) | set(solo.CHAR_MODELS)))))
        # soldier behaviour: stand (default), chase (attack order on the player), patrol (walk the path_corner chain from 'target')
        corners = {e.get('targetname'): e for e in ents_of('path_corner') if e.get('targetname')}
        wps = []
        for n, (foe, e) in enumerate(zip(foes, ents_of('npc_soldier'))):
            beh = (e.get('behavior') or 'stand').lower()
            if beh == 'chase': foe['order'] = ('follow', 30)       # follow order on the player
            elif beh == 'rush':       # run to the named path_corner, or to where the player starts
                c = corners.get(e.get('target'))
                if c is not None: v = vec(c.get('origin', '0 0 0')); foe['order'] = ('reach', (v[0], v[1], v[2] + 1.0))
                else: foe['order'] = ('reach', (o[0], o[1], o[2]))
            elif beh == 'patrol':
                first = corners.get(e.get('target'))
                if not first: print('WARNING: patrolling npc_soldier needs target = name of a path_corner'); continue
                def gpos(c):
                    v = vec(c.get('origin', '0 0 0')); return (v[0], v[1], v[2] + 1.0)
                foe['order'] = ('reach', gpos(first))
                seen = set(); cur = first
                while cur is not None and id(cur) not in seen:
                    seen.add(id(cur)); nxt = corners.get(cur.get('target'))
                    if nxt is not None:
                        c = gpos(cur)
                        wps.append(dict(name='wp_%02d_%02d' % (len(wps) + 1, n + 1), kind='waypoint', soldier='id_character_enemy_%02d' % (n + 1), goto=gpos(nxt),
                                        lo=(c[0] - 6, c[1] - 6, c[2] - 3), hi=(c[0] + 6, c[1] + 6, c[2] + 30)))
                    cur = nxt
        FRIENDS = {'cecile': 'id_character_t00_cecile', 'mitchel': 'id_character_mitchel'}
        for e in ents_of('npc_friend'):       # friendly characters from level 1 (they fight on your side)
            v = vec(e.get('origin', '0 0 0'))
            foe = dict(model=e.get('model') or None, pos=(v[0], v[1], v[2] + 1.0), yaw=angle_props(float(e.get('angle', 0)))[1], template=FRIENDS.get(e.get('who') or 'cecile', FRIENDS['cecile']),
                       keep=True, hold=(e.get('behavior') or 'follow') == 'stand', health=float(e.get('health') or 200), tname=e.get('targetname') or None)
            if str(e.get('hidden') or '0') in ('1', 'yes', 'true'): foe['after'] = [(11, 1)]
            if (e.get('behavior') or 'follow') == 'follow': foe['order'] = ('follow', int(float(e.get('distance') or 85)))
            if foe['model'] and foe['model'] not in solo.MODELS and foe['model'] not in solo.CHAR_MODELS: sys.exit('npc_friend: unknown model %r' % foe['model'])
            foes.append(foe)
        doors = []
        for e in ents_of('door'):
            mdl = e.get('model', 'blindee') or 'blindee'
            if mdl not in solo.DOOR_MODELS: sys.exit('door: unknown model ' + mdl)
            _, hw, hh = solo.DOOR_MODELS[mdl]
            c = vec(e.get('origin', '0 0 0')); c[2] += hh           # origin = bottom centre of the door
            dyaw = float(e.get('angle', 0)) - 90.0                    # door plane runs across the facing direction
            dist = float(e.get('distance', 0) or 0) * SCALE or (2 * hh if e.get('slide') in ('up', 'down') else 2 * hw)
            r = math.radians(dyaw); side = (math.cos(r), math.sin(r), 0.0)
            dv = {'left': side, 'right': tuple(-x for x in side), 'up': (0, 0, 1), 'down': (0, 0, -1)}[e.get('slide', 'left') or 'left']
            doors.append(dict(tname=e.get('targetname') or None, locked=str(e.get('locked') or '0') in ('1', 'yes', 'true'), model=mdl, yaw=dyaw, closed=tuple(c), open=tuple(c[i] + dv[i] * dist for i in range(3)),
                              speed=float(e.get('speed', 0.3) or 0.3), wait=float(e.get('wait', 3) or 3), range=float(e.get('range', 50) or 50)))
        fogs = []
        for e in ents_of('env_fog'):
            fcol = [float(x) for x in (e.get('color') or '0.85 0.85 0.85').split()[:3]]
            if max(fcol) > 1.0: fcol = [x / 255.0 for x in fcol]
            fogs.append(dict(name=(e.get('targetname') or 'fog_%02d' % (len(fogs) + 1)).strip(), pos=tuple(vec(e.get('origin', '0 0 0'))), near=float(e.get('near', 400) or 400), far=float(e.get('far', 4000) or 4000), h1=float(e.get('height_a', -400) or -400), h2=float(e.get('height_b', 800) or 800), color=tuple(fcol)))
        fog_names = [f['name'] for f in fogs]
        if len(fogs) > 8: print('WARNING: at most 8 env_fog; extra ignored'); fogs = fogs[:8]
        STOCK_DRT = ['XX1DRT0011', 'XX1DRT0012', 'XX3DRT0031', 'XX4DRT0041', 'XX4DRT0042', 'XX5DRT0051', 'XX5DRT0052', 'XX6DRT0061', 'XX6DRT0062']
        drts = []
        for e in ents_of('info_drt'):        # D.R.T. computer: the terminal plays its movies (stock .4xm in movies\) when the player uses it
            mv = [m if m.lower().endswith('.4xm') else m + '.4xm' for m in (e.get('movie') or 'XX1DRT0011').replace(',', ' ').split()][:6]
            for m in mv:
                if m[:-4].upper() not in STOCK_DRT: print('NOTE: info_drt movie %r is not one of the stock D.R.T. movies (%s)' % (m, ', '.join(STOCK_DRT)))
            drts.append(dict(pos=tuple(vec(e.get('origin', '0 0 0'))), yaw=(float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0, movies=mv,
                             time=float(e.get('time') or 3000)))
        def _yaw(e): return (float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0
        def _f(e, k):
            v = str(e.get(k, '')).strip()
            return float(v) if v else None
        turrets = []
        for e in ents_of('npc_turret'):      # automatic machine-gun turret (auto_mg)
            t = dict(friendly=str(e.get('friendly', '0')).strip() not in ('', '0'), pos=tuple(vec(e.get('origin', '0 0 0'))), yaw=_yaw(e), active=str(e.get('active', '0')).strip() not in ('', '0'), tname=e.get('targetname') or None)   # off until the alarm (script: alarm on / turret NAME on)
            for k in ('yaw_min', 'yaw_max', 'rate', 'health'):
                if _f(e, k) is not None: t[k] = _f(e, k)
            turrets.append(t)
        dogs = []
        for e in ents_of('npc_dog'):         # attack dog; explosive 1 = the level 4 bomb dogs
            d = dict(friendly=str(e.get('friendly', '0')).strip() not in ('', '0'), pos=tuple(vec(e.get('origin', '0 0 0'))), yaw=_yaw(e), explosive=str(e.get('explosive', '0')).strip() not in ('', '0'))
            for k in ('range', 'health', 'damage'):
                if _f(e, k) is not None: d[k] = _f(e, k)
            dogs.append(d)
        # ambient sounds + music: wav = a stock sound file name (any .wav in the game's .ibf archives) or a .wav in the map's sounds\ folder
        sound_dir = os.path.join(os.path.dirname(os.path.abspath(a.map)), 'sounds')
        stock_waves = set()
        for _l in ('Others.lst', 'Needed.lst', 'Models.lst'):
            try: stock_waves |= {x.lower() for x in re.findall(r'[^\0\\/]+?\.wav', open(os.path.join(game, _l), 'rb').read().decode('latin1'), re.I)}
            except OSError: pass
        custom_waves = {}
        def wave_file(w, what):
            w = w.strip()
            if not w.lower().endswith('.wav'): w += '.wav'
            p = os.path.join(sound_dir, w)
            if os.path.exists(p): custom_waves[w] = open(p, 'rb').read(); return 'sounds\\custom\\' + w
            if stock_waves and w.lower() not in stock_waves: print('WARNING: %s: %r is not a stock sound and not in the map\'s sounds folder' % (what, w))
            return 'sounds\\' + w
        sounds = []; swho = {}
        for e in ents_of('ambient_sound'):
            if not (e.get('wav') or '').strip(): print('WARNING: ambient_sound without a wav key, skipped'); continue
            var = 'id_sound_snd_%02d' % (len(sounds) + 1)
            near = float(e.get('radius') or 300) * SCALE
            loops = str(e.get('loop', '1')).strip()
            sounds.append(dict(var=var, file=wave_file(e['wav'], 'ambient_sound'), pos=tuple(vec(e.get('origin', '0 0 0'))), volume=float(e.get('volume') or 1),
                               near=near, far=float(e.get('falloff') or 0) * SCALE or near * 2, loop=-1 if loops in ('1', '') else 1, on=str(e.get('start_on', '1')).strip() not in ('0',)))
            if e.get('targetname'): swho[e['targetname']] = var
        if (world.get('music') or '').strip():      # music: a looping sound that is equally loud everywhere (huge range), at the player start
            sounds.append(dict(var='id_sound_snd_music', file=wave_file(world['music'], 'worldspawn music'), pos=None, volume=float(world.get('music_volume') or 1),
                               near=1e6, far=2e6, loop=-1, on=str(world.get('music_start', '1')).strip() not in ('0',)))
        helis = []
        for e in ents_of('npc_helicopter'):  # helicopter (allies or enemy transport); steered by the script commands heli_move, heli_start, ...
            hk = (e.get('kind') or 'allies').strip().lower()
            if hk not in ('allies', 'enemy'): print('WARNING: npc_helicopter kind %r (allies or enemy)' % hk); hk = 'allies'
            hn = (e.get('targetname') or 'heli%d' % (len(helis) + 1)).strip()
            helis.append(dict(pos=tuple(vec(e.get('origin', '0 0 0'))), kind=hk, name=hn))
        mguns = []
        for e in ents_of('weapon_mounted_mg'):   # mounted gun the player can use; kind = bunker, handles, launcher, launcher_stand, desk
            mk = (e.get('kind') or 'bunker').strip().lower()
            if mk not in ('bunker', 'handles', 'launcher', 'launcher_stand', 'desk'): print('WARNING: weapon_mounted_mg kind %r (bunker, handles, launcher, launcher_stand, desk)' % mk); mk = 'bunker'
            mg = dict(pos=tuple(vec(e.get('origin', '0 0 0'))), yaw=_yaw(e), kind=mk)
            if _f(e, 'pitch_range') is not None or _f(e, 'yaw_range') is not None:
                mg['arc'] = (_f(e, 'pitch_range') or 90.0, 0.0, _f(e, 'yaw_range') or 90.0)
            mguns.append(mg)
        docs = []
        for e in ents_of('info_document'):   # a document the player can pick up and read: text = Trad.ibf text id (stock: XX1DOCU000 .. XX6DOCU001)
            docs.append(dict(pos=tuple(vec(e.get('origin', '0 0 0'))), yaw=(float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0,
                             text=(e.get('text') or 'XX1DOCU002').strip()))
        FX_KINDS = {'steam': (7, 5, 1.0), 'gas': (1, 5, 6.0), 'gas_small': (1, 4, 5.0)}
        fx = []
        for e in ents_of('env_particle'):
            fxname = (e.get('effect') or 'steam').strip().lower()
            if fxname not in FX_KINDS: print('WARNING: env_particle: unknown effect %r (%s)' % (fxname, ', '.join(FX_KINDS))); continue
            fxscale = float(e.get('scale') or 0) or FX_KINDS[fxname][2]
            fxang = tuple(float(x) for x in (e.get('angles') or '0 0 0').split()[:3])
            fx.append(dict(pos=tuple(vec(e.get('origin', '0 0 0'))), kind=FX_KINDS[fxname][0], variant=FX_KINDS[fxname][1], scale=fxscale, angles=fxang))
        health = []
        items = []
        props = []
        _stock_models = None
        for e in ents_of('prop_static'):
            mf = (e.get('model') or 'OBJ_bidon').strip()
            if '.' not in mf: mf += '.4x3'
            if _stock_models is None:
                try: _stock_models = {x.lower() for x in re.findall(r'[^\0\\/]+?\.4[xX]3', open(lst, 'rb').read().decode('latin1'))}
                except OSError: _stock_models = set()
            if _stock_models and mf.lower() not in _stock_models and not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(a.map)), 'models', mf)):
                print('WARNING: prop_static model %r is not in Models.lst and not in the map\'s models folder' % mf)
            pang = tuple(float(x) for x in (e.get('angles') or '0 0 0').split()[:3])
            pmode = (e.get('mode') or 'static').strip().lower()
            if pmode not in ('static', 'breakable', 'crate', 'metal_crate', 'vent', 'plank'): print('WARNING: prop_static mode %r (use static, breakable, crate, metal_crate, vent or plank)' % pmode); pmode = 'static'
            ppos = tuple(vec(e.get('origin', '0 0 0')))
            props.append(dict(pos=ppos, angles=pang, model=mf, mode=pmode, node=(e.get('node') or '').strip()))
            # what the prop hides: loose pickups at its origin (the campaign's crates do this). 'drop' = space separated names or item numbers
            DROPS = {'medikit': 0, 'health': 0, 'small_medikit': 1, 'small_health': 1, 'mg_ammo': 2, 'ammo_mg': 2, 'sniper_ammo': 3, 'snipe_ammo': 3, 'shotgun_ammo': 4,
                     'handgun_ammo': 5, 'launcher_ammo': 6, 'rocket_ammo': 7, 'flame_ammo': 8, 'mg3_ammo': 9}
            dl = (e.get('drop') or '').replace(',', ' ').split()
            pdrop = float(e.get('drop_health') or 0)       # older key: 1 = small medikit, 2+ = medikit
            if pdrop > 0: dl.append('small_medikit' if pdrop < 2 else 'medikit')
            if dl and pmode == 'static': print('WARNING: prop_static drop needs a breakable mode'); dl = []
            for q, d in enumerate(dl):
                t = DROPS.get(d.lower(), int(d) if d.lstrip('-').isdigit() else None)
                if t is None: print('WARNING: prop_static drop %r unknown (%s or an item number)' % (d, ', '.join(DROPS))); continue
                items.append(dict(pos=(ppos[0] + 1.0 * (q % 2), ppos[1] + 1.0 * (q // 2), ppos[2] - 0.5), type=t, hold=len(props),
                                  rot=(pang[1], 92.0, -90.0) if t in (0, 1) else (pang[1], 0.0, 0.0)))   # medikits lie on their side like the campaign's, or they stick out of the crate
        for e in ents_of('item_health'):
            o2 = vec(e.get('origin', '0 0 0')); o2[2] += ARMORY_LIFT
            health.append(dict(pos=tuple(o2), yaw=(float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0, amount=float(e.get('amount', 3) or 3)))
        for e in ents_of('item_crate'):
            o2 = vec(e.get('origin', '0 0 0')); o2[2] += ARMORY_LIFT
            slots, mags, medic = [-1]*4, [0]*4, False
            n = 0
            for q in range(1, 5):
                v = int(e.get('item_%d' % q, -1) or -1) if str(e.get('item_%d' % q, '')).strip() != '' else -1
                if v == 0: medic = True
                elif v > 0 and n < 4:
                    slots[n] = v; mags[n] = int(e.get('ammo_%d' % q, 4) or 4) if str(e.get('ammo_%d' % q, '')).strip() != '' else 4; n += 1
            health.append(dict(pos=tuple(o2), yaw=(float(e.get('angle', 0)) + YAW_OFFSET + SOLO_TURN) % 360.0,
                               amount=float(e.get('amount', 3) or 3), slots=slots, mags=mags, medic=medic))
        weapons = []
        for e in ents_of('item_weapon'):
            o2 = vec(e.get('origin', '0 0 0')); o2[2] += 1.0
            weapons.append(dict(pos=tuple(o2), yaw=float(e.get('angle', 0)) + SOLO_TURN, weapon=int(e.get('weapon', 4) or 4),
                                ammo=int(e.get('ammo', -1) if e.get('ammo', '') != '' else -1)))
        for e in ents_of('item_pickup'):
            o2 = vec(e.get('origin', '0 0 0')); o2[2] += 0.5
            t = int(e.get('custom', -1) or -1)
            items.append(dict(pos=tuple(o2), yaw=float(e.get('angle', 0)) + SOLO_TURN, type=t if t >= 0 else int(e.get('type', 0) or 0)))
        zones = []                       # kill / hurt volumes: a brush entity becomes an event box plus script functions
        for e in ents:
            cls = e['props'].get('classname', '')
            kind = {'trigger_kill': 'kill', 'trigger_end': 'end', 'trigger_save': 'save', 'trigger_script': 'script', 'trigger_weather': 'weather'}.get(cls)
            if not kind or not e['brushes']: continue
            pts = [p for brush in e['brushes'] for f, n, poly in mapfile.brush_polygons(brush) for p in poly]
            lo = sc([min(p[i] for p in pts) for i in range(3)]); hi = sc([max(p[i] for p in pts) for i in range(3)])
            zones.append(dict(name='%s_%02d' % (kind, len(zones) + 1), kind=kind, lo=tuple(lo), hi=tuple(hi),
                              next=NEXT if (e['props'].get('next') or '').strip() == 'next' else int(float(e['props'].get('next', 0) or 0)), tname=e['props'].get('targetname') or None,
                              **({k: (e['props'].get(k) or '').strip() for k in ('enter_atmosphere', 'exit_atmosphere', 'enter_sky', 'exit_sky')} if kind == 'weather' else {})))
            if kind == 'weather':
                z = zones[-1]
                for k in ('enter_atmosphere', 'exit_atmosphere'):
                    if z[k] and z[k] not in ('space', 'rain', 'neige', 'neige_legere', 'tempete', 'SPACE'): print('WARNING: trigger_weather: unknown atmosphere %r (stock: space, rain, neige, neige_legere, tempete)' % z[k])
                for k in ('enter_sky', 'exit_sky'):
                    if z[k] and z[k] not in ('sky_LV_01', 'sky_LV_02', 'sky_LV_02_02-03', 'sky_LV_03', 'sky_LV_05', 'sky_LV_05_06', 'set_sky_none'): print('WARNING: trigger_weather: unknown sky %r' % z[k])
                fogc = {}
                for ph in ('enter', 'exit'):
                    nm_ = (e['props'].get(ph + '_fog') or '').strip()
                    if not nm_: continue
                    if nm_ not in fog_names: print('WARNING: trigger_weather: %s_fog %r is not the targetname of any env_fog (%s)' % (ph, nm_, ', '.join(fog_names) or 'none'))
                    fogc[ph] = [('fog', [('str', nm_)])]
                if fogc:
                    zones.append(dict(name='script_%02d' % (len(zones) + 1), kind='script', lo=tuple(lo), hi=tuple(hi), next=0, tname=None, auto=True, cmds=fogc.get('enter', []), leave_cmds=fogc.get('exit', [])))
                    need_fog = True
                if not any(z[k] for k in ('enter_atmosphere', 'exit_atmosphere', 'enter_sky', 'exit_sky')):
                    zones.remove(z)
                    if not fogc: print('WARNING: a trigger_weather has nothing set and does nothing')
        zones += wps
        buttons = []                     # func_button brushes: drawn like func_detail, plus a use-trigger at the centre
        for e in ents:
            if e['props'].get('classname') != 'func_button' or not e['brushes']: continue
            tn = (e['props'].get('targetname') or '').strip()
            if not tn: print('WARNING: a func_button has no targetname and is only decoration'); continue
            pts = [p for brush in e['brushes'] for f, n, poly in mapfile.brush_polygons(brush) for p in poly]
            lo = sc([min(p[i] for p in pts) for i in range(3)]); hi = sc([max(p[i] for p in pts) for i in range(3)])
            rng = float(e['props'].get('range') or 0) * SCALE or 24.0
            buttons.append(dict(name='btn_' + tn.lower(), tname=tn, pos=tuple((lo[i] + hi[i]) / 2 for i in range(3)), yaw=angle_props(float(e['props'].get('angle') or 0))[0],
                                range=rng, cone=float(e['props'].get('cone') or 90), cmds=[]))
        spath = os.path.splitext(os.path.abspath(a.map))[0] + '.script'
        starts = []; deaths = []
        if os.path.exists(spath):      # the map's script file: commands run at level start or when the player enters a trigger_script zone
            from ismap import script as scriptlib
            sname = os.path.basename(spath)
            try: blocks = scriptlib.parse(open(spath, encoding='utf-8').read())
            except ValueError as err: sys.exit('%s: %s' % (sname, err))
            who = {f['tname']: 'id_character_enemy_%02d' % (i + 1) for i, f in enumerate(foes) if f.get('tname')}
            names = [f['tname'] for f in foes if f.get('tname')]
            hwho = {h['name']: 'id_helico_map_%02d' % (i + 1) for i, h in enumerate(helis)}
            twho = {t['tname']: 'id_auto_mg_map_%02d' % (i + 1) for i, t in enumerate(turrets) if t.get('tname')}
            dwho = {d['tname']: 'id_door_custom_%02d' % (i + 1) for i, d in enumerate(doors) if d.get('tname')}
            for nme in sorted({x for x in names if names.count(x) > 1}): print('WARNING: %s: several characters are named %r; the script uses the last one' % (sname, nme))
            def typed(cmd, args):
                if cmd == 'native':
                    out = [('str', args[0])]
                    for x in args[1:]:
                        if x in who: out.append(('npc', who[x]))
                        elif x == 'player': out.append(('player', None))
                        elif scriptlib._num(x): out.append(('num', float(x)))
                        else: out.append(('str', x.strip('"')))
                    return out
                out = []; i = 0
                for kind in scriptlib.SPEC[cmd]:
                    k = kind.rstrip('?')
                    if i >= len(args): break
                    if k == 'npc':
                        if args[i] not in who: sys.exit('%s: no npc_soldier/npc_friend with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        out.append(('npc', who[args[i]])); i += 1
                    elif k == 'pos' and not scriptlib._num(args[i]):
                        c = corners.get(args[i])
                        if c is None: sys.exit('%s: no path_corner with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        v = vec(c.get('origin', '0 0 0')); out += [('num', v[0]), ('num', v[1]), ('num', v[2] + 1.0)]; i += 1
                    elif k == 'pos':
                        v = vec(' '.join(args[i:i+3])); out += [('num', v[0]), ('num', v[1]), ('num', v[2] + 1.0)]; i += 3
                    elif k == 'int': out.append(('int', str(NEXT) if args[i] == 'next' else args[i])); i += 1
                    elif k in ('var', 'op'): out.append(('str', args[i])); i += 1
                    elif k == 'door':
                        if args[i] not in dwho: sys.exit('%s: no door with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        out.append(('door', dwho[args[i]])); i += 1
                    elif k == 'heli':
                        if args[i] not in hwho: sys.exit('%s: no npc_helicopter with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        out.append(('heli', hwho[args[i]])); i += 1
                    elif k == 'onoff': out.append(('int', '1' if args[i] == 'on' else '0')); i += 1
                    elif k == 'sound':
                        if args[i] not in swho: sys.exit('%s: no ambient_sound with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        out.append(('sound', swho[args[i]])); i += 1
                    elif k == 'turret':
                        if args[i] not in twho: sys.exit('%s: no npc_turret with targetname %r (in "%s %s")' % (sname, args[i], cmd, ' '.join(args)))
                        out.append(('turret', twho[args[i]])); i += 1
                    elif k in ('num', 'fnum'): out.append(('num', float(args[i]))); i += 1
                    else:
                        if k == 'name' and cmd == 'sky' and args[i] not in scriptlib.SKIES: print('WARNING: %s: unknown sky %r (stock skies: %s)' % (sname, args[i], ', '.join(scriptlib.SKIES)))
                        if k == 'name' and cmd == 'atmosphere' and args[i] not in scriptlib.ATMOSPHERES: print('WARNING: %s: unknown atmosphere %r (stock: %s)' % (sname, args[i], ', '.join(scriptlib.ATMOSPHERES)))
                        out.append(('str', args[i])); i += 1
                return out
            for b in blocks:
                cmds = [(c, typed(c, a_)) for c, a_ in b['cmds']]
                if b['kind'] == 'start': starts.append(cmds); continue
                if b['kind'] == 'dead':
                    for x in b['zone']:
                        if x not in who: sys.exit('%s: on dead: no npc_soldier/npc_friend with targetname %r' % (sname, x))
                    deaths.append(([who[x] for x in b['zone']], cmds)); continue
                if b['kind'] == 'use':
                    bt = next((x for x in buttons if x['tname'] == b['zone']), None)
                    if bt is None: sys.exit('%s: no func_button with targetname %r in the map' % (sname, b['zone']))
                    bt['cmds'] = cmds; bt['once'] = b['once']; continue
                z = next((z for z in zones if z['kind'] == 'script' and z.get('tname') == b['zone']), None)
                if z is None: sys.exit('%s: no trigger_script with targetname %r in the map' % (sname, b['zone']))
                if b['kind'] == 'leave': z['leave_cmds'] = cmds; continue
                z['once'] = b['once']; z['cmds'] = cmds
            for bt in buttons:
                if not bt['cmds']: print('WARNING: func_button %r has no "on use" block in %s' % (bt['tname'], sname))
            used = {b['zone'] for b in blocks if b['kind'] in ('enter', 'leave')}
            for d in doors:
                if d['locked'] and not any(c in ('open',) for c in [c for b in blocks for c, _ in b['cmds']]): print('WARNING: a locked door is never opened by the script')
            for z in zones:
                if z['kind'] == 'script' and not z.get('auto') and z.get('tname') not in used: print('WARNING: trigger_script %r has no "on enter" or "on leave" block in %s' % (z.get('tname'), sname))
            print('script file: %d blocks' % len(blocks))
        zones = [z for z in zones if z['kind'] != 'script' or z.get('cmds') or z.get('leave_cmds')]
        allcmds = (['wait'] if deaths else []) + [c for d in deaths for c, _ in d[1]] + [c for z in zones for c, _ in z.get('cmds', []) + z.get('leave_cmds', [])] + [c for bt in buttons for c, _ in bt.get('cmds', [])] + [c for blk in starts for c, _ in blk]
        uses_weather = 'atmosphere' in allcmds or any(z['kind'] == 'weather' and (z.get('enter_atmosphere') or z.get('exit_atmosphere')) for z in zones)
        if 'fog' in allcmds and not fogs: print('WARNING: fog commands used but the map has no env_fog')
        if uses_weather and not fogs:    # without a fog entity the game draws snow black (found by testing); a very distant fog fixes it without visibly fogging the map
            print('note: weather used without an env_fog: adding an invisible distant fog (the game draws snow black when the map has no fog)')
            fogs.append(dict(name='fog_default', pos=(0.0, 0.0, 0.0), near=30000.0, far=50000.0, h1=-400.0, h2=800.0, color=(0.85, 0.85, 0.85)))
        if 'wait' in allcmds or fx or len(fogs) > 1 or any(i.get('hold') for i in items) or any(t['active'] for t in turrets):      # 'wait' (and restarting particle effects) needs a clock: an event box around the whole map, ticked every frame while the player is in it
            wp = [p for brush in [b for e in ents for b in e['brushes']] for f, n_, poly in mapfile.brush_polygons(brush) for p in poly]
            wlo = sc([min(p[i] for p in wp) - 64 for i in range(3)]); whi = sc([max(p[i] for p in wp) + 64 for i in range(3)])
            zones.append(dict(name='clock', kind='tick', lo=tuple(wlo), hi=tuple(whi)))
        from ismap import nav
        seeds = [[float(x) for x in e.get('origin', '0 0 0').split()] for e in ents_of('info_player_start', 'npc_soldier', 'info_player_deathmatch')]
        _dg = Gex(open(donor, 'rb').read())
        if world.get('sky'):
            for i, names in _dg.calls('set_sky'): _dg.set_const(i, 1, world.get('sky'))
        donor_bytes = _dg.tobytes()
        icp, nn = nav.build(floor_polys, solid_brushes, SCALE, float(world.get('navgrid', 96)), seeds=seeds)
        if icp: outputs['test.icp'] = icp
        waters = []
        if water_ents:        # func_water: one WATER entity per func_water; the surface is a flat grid model (the engine ripples its vertices)
            from ismap import watermodel
            for wn, we in enumerate(water_ents.values()):
                wp = we['props']
                pts = [p for t, _ in we['tris'] for p in t]
                org = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[2] for p in pts))
                rel = [(a_, b_, c_, u0, u1, u2) for (a_, b_, c_), (u0, u1, u2) in [(tuple(tuple(p_[i] - org[i] for i in range(3)) for p_ in t), uv) for t, uv in we['tris']]]
                im, _ = water_imgs[we['tex']]
                gname = 'water_' + we['tex'].split('/')[-1].replace(' ', '_')[:40] + '.tga'
                fn = '%s_water%02d.4x3' % (name, wn + 1)
                op = float(str(wp.get('opacity') or world.get('glass_opacity') or 0.6))
                tmp = os.path.join(HERE, 'build', '_water.4x3'); os.makedirs(os.path.dirname(tmp), exist_ok=True)
                data_w, ntri = watermodel.build(tmp, rel, gname, im, op, step=float(wp.get('grid') or 24) * SCALE)
                water_models[fn] = data_w
                tint = str(wp.get('tint') or '').split()
                if len(tint) >= 3:
                    tint = [float(x) for x in tint[:3]]
                    if max(tint) > 1.0: tint = [x / 255.0 for x in tint]
                else:       # the texture's average colour, darkened
                    sm = im.convert('RGB').resize((1, 1)).getpixel((0, 0)); tint = [x / 255.0 * 0.6 for x in sm]
                waters.append(dict(file=fn, pos=org, tint=tint, speed=float(wp.get('speed') or 0.15), depth=float(wp.get('depth') or 10), height=float(wp.get('height') or 50)))
                print('water: %s (%d triangles, speed %.2f)' % (fn, ntri, waters[-1]['speed']))
        data, n = solo.build_mp(outputs[name + '_dm.gex'], donor_bytes, (o[0], o[1], o[2] + 1.0), angle_props(yaw)[1], enemies=foes, doors=doors, zones=zones, health=health, items=items, weapons=weapons, starts=starts, deaths=deaths, player_model=world.get('player_model') or None, fogs=fogs, fx=fx, props=props, drts=drts, docs=docs, turrets=turrets, dogs=dogs, mguns=mguns, alarm=any(c == 'alarm' for c in allcmds), helis=helis, sounds=sounds, waters=waters, loadout=loadout, ammo=ammo, buttons=[b for b in buttons if b['cmds']],
                                checkpoints=(('levels\\multi\\test\\test' if name == 'test' else 'levels\\campaign\\level%s\\lv%s' % (name[2:], name[2:])) if icp else None))   # character facing uses the respawn's second angle (z - 90)
        g = Gex(data)    # (the world sky was already set in the donor's client_init above; script/zone set_sky calls must stay as written)
        outputs = {name + '.gex': g.tobytes(), **({name + '.icp': icp} if icp else {})}
        # per-level settings for ISModLoader (IronStormConsole.exe / launcher): first-person arms of player_model
        from ismap import modpack as _mp
        _pm = world.get('player_model') or ''
        outputs[name + '.ismod'] = ('player_model=%s\narms=%s\n' % (_pm, _mp.ARMS.get(_pm, _mp.ARMS_FILE))).encode()
        print('single-player script: player start %s, yaw %s, %d enemies, %d doors, %d zones, %d health crates, %d pickups, %d loose weapons (%d instructions)' % ([round(v) for v in o], yaw, len(foes), len(doors), len(zones), len(health), len(items), len(weapons), n))
    # ---------------- write
    out = a.out or os.path.join(HERE, 'build', name)
    os.makedirs(os.path.join(out, 'levels', 'multi', name), exist_ok=True)
    os.makedirs(os.path.join(out, 'models'), exist_ok=True)
    scene_path = os.path.join(out, 'models', name + '.4x3')
    write_map(scene_path, head, recs, tags)
    light = bigfile.read_file(ibf, lst, TEMPLATE + '_light.4x3')
    if light is None: sys.exit('could not read %s_light.4x3 from Models.ibf' % TEMPLATE)
    if True:     # always rebuild: the template's own dynamic lights (isdm3) must not leak into this map
        from ismap import lights as lightlib
        def col(v):
            c = [float(x) for x in str(v).split()][:3] if v else [255, 255, 255]
            c = c + [255] * (3 - len(c))
            return tuple(x / 255.0 if max(c) > 1.0 else x for x in c)
        ll = [dict(pos=vec(e.get('origin', '0 0 0')), rgb=col(e.get('_color')), mul=float(e.get('light', 1.0)),
                   start=float(e.get('start', 0)) * SCALE, end=float(e.get('range', 400)) * SCALE) for e in lamps]
        sunpos = (vec(suns[0].get('origin', '0 0 0')), None) if suns else None
        light = lightlib.build(light, ll, sunpos)
        if ll: print('lights: %d' % len(ll))
    open(os.path.join(out, 'models', name + '_light.4x3'), 'wb').write(light)
    for fn, data in outputs.items(): open(os.path.join(out, 'levels', 'multi', name, fn), 'wb').write(data)
    print('wrote', out)
    print('spawns %d, armories %d, bounds %s .. %s' % (len(spawns), len(armories), [round(v) for v in mn], [round(v) for v in mx]))

    if a.install:
        multi = os.path.join(game, 'levels', 'multi')
        dest = os.path.join(multi, name)
        if name in ('isdm1', 'isdm2', 'isdm3', 'isdm4', 'isctf1', 'isctf2', 'isctf3', 'isctf4'):
            sys.exit('refusing to overwrite stock map ' + name)
        os.makedirs(dest, exist_ok=True) if name == 'test' or not SOLO else None
        if name != 'test' and SOLO:      # a campaign level slot: the script and nav graph go to levels\\campaign\\levelN
            cdest = os.path.join(game, 'levels', 'campaign', 'level' + name[2:]); os.makedirs(cdest, exist_ok=True)
            for fn, data in outputs.items():
                if fn.startswith(name + '.'):
                    tgt = os.path.join(cdest, fn.replace(name, 'lv' + name[2:], 1))
                    if os.path.exists(tgt) and not os.path.exists(tgt + '.stock'): shutil.copy2(tgt, tgt + '.stock')   # keep the stock level's file
                    open(tgt, 'wb').write(data)
            print('installed as campaign level %s: %s' % (name[2:], cdest))
            dest = None
        if dest:
            for fn, data in outputs.items(): open(os.path.join(dest, fn), 'wb').write(data)
        files = {name + '.4x3': open(scene_path, 'rb').read(), name + '_light.4x3': light, **water_models}
        if SOLO:   # single player needs an event-box scene, or saving crashes (borrow the tiny one from isdm1)
            eb = bigfile.read_file(ibf, lst, 'isdm1_event_boxes.4X3')
            if zones:
                from ismap import eventbox
                eb = eventbox.build([(z['name'], z['lo'], z['hi']) for z in zones])
            if eb: files[name + '_event_boxes.4X3'] = eb
            # first-person arms follow worldspawn player_model when that character has arms (one file for the whole game)
            ARMS = {'kasakh': 'kasakh_model_first.4x3', 'lobby': 'Lobby_model_first.4x3', 'russian': 'russian_model_first.4x3',
                    'sibbourrin1': 'sibbourrin1_model_first.4x3', 'sibsniper': 'sibsniper_model_first.4x3',
                    'supercadet': 'supercadet_model_first.4x3', 'trooper': 'trooper_model_first.4x3'}
            pm = world.get('player_model') or ''
            arms = ARMS.get(pm, 'wiz_model_first.4x3')
            si, sl = (ibf + '.bak', lst + '.bak') if os.path.exists(ibf + '.bak') else (ibf, lst)
            ad = bigfile.read_file(si, sl, 'wiz_model_first.4x3')      # keep the stock arms in the archive: ISModLoader picks
            if ad is not None: files['wiz_model_first.4x3'] = ad          # the level's arms at load time from <level>.ismod
            print('first-person arms: %s' % (pm if pm in ARMS else 'normal' + (' (%s has no arms model)' % pm if pm else '')))
        n = bigfile.replace_files(ibf, lst, files)
        if SOLO:     # test runs: the loader reads the map's own .wav files straight from its sounds folder (path in ismod_test_sounds.txt)
            tl = os.path.join(game, 'ismod_test_sounds.txt')
            if custom_waves: open(tl, 'w').write(sound_dir + '\\\n'); print('sounds: %s from %s' % (', '.join(sorted(custom_waves)), sound_dir))
            elif os.path.exists(tl): os.remove(tl)
        maps = [d for d in os.listdir(multi) if os.path.isdir(os.path.join(multi, d))]
        print('installed %s (Models.ibf now has %d files)' % (name, n))
        if len(maps) > 10: print('WARNING: %d map folders in levels\\multi; the menu breaks above 10' % len(maps))
    if a.install and name == 'test':      # TrenchBroom test runs: plugins\\ next to the map -> build\\test_plugins
        from ismap import plugins as plg
        tp = os.path.join(HERE, 'build', 'test_plugins'); shutil.rmtree(tp, ignore_errors=True)
        psrc = os.path.join(os.path.dirname(os.path.abspath(a.map)), 'plugins')
        if os.path.isdir(psrc):
            os.makedirs(tp, exist_ok=True)
            for f in os.listdir(psrc):
                if f.lower().endswith('.dll'): shutil.copyfile(os.path.join(psrc, f), os.path.join(tp, f))
            plg.compile_dir(psrc, os.path.join(tp, 'map_plugin.dll'))
    if a.package:
        from ismap import modpack
        mfiles = {name + '.4x3': open(scene_path, 'rb').read(), name + '_light.4x3': light, **water_models}
        if SOLO:
            eb = bigfile.read_file(ibf, lst, 'isdm1_event_boxes.4X3')
            if zones:
                from ismap import eventbox
                eb = eventbox.build([(z['name'], z['lo'], z['hi']) for z in zones])
            if eb: mfiles[name + '_event_boxes.4X3'] = eb
            level = {fn: data for fn, data in outputs.items() if fn.startswith(name + '.')}
            pmn = world.get('player_model') or ''
        else:                                    # multiplayer map: all its game-mode scripts
            level = dict(outputs)
        root = modpack.write(game, a.package, name, mfiles, level, None, a.title, a.description, mp=not SOLO, sounds=custom_waves if SOLO else None)
        print('packaged as %s (%s %s): %s' % (a.package, 'multiplayer map' if not SOLO else 'slot', name, root))
    return 0

if __name__ == '__main__':
    sys.exit(main())
